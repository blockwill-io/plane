# BlockWill fork — Plane Query Language (PQL) for the v1 API.
#
# Plane Cloud/Enterprise accept a `pql` query parameter on the work item list
# and count endpoints; Community Edition rejects it. The Plane MCP server (and
# so Claude) writes PQL, so this module parses it and compiles it to a Django
# Q object over Issue. Grammar and vocabulary follow the reference the MCP
# server hands to the model (plane_mcp/pql_reference.py in plane-mcp-server).
#
#   expr   := or
#   or     := and (OR and)*
#   and    := not (AND not)*
#   not    := NOT not | '(' expr ')' | predicate() | relation("X") | comparison
#   comparison := field op value
#               | field [NOT] IN (list | listFunction())
#               | field IS [NOT] (NULL | EMPTY)
#               | field BETWEEN value AND value | field BETWEEN (value, value)
#
# Multi-valued relations (assignee, label, cycle, ...) compile to
# `id IN (subquery)` so NOT and != mean "has no such row", and a row in a join
# table that was soft-deleted never matches.

import re
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta

import pytz
from dateutil.relativedelta import relativedelta
from django.db.models import Exists, OuterRef, Q
from django.utils import timezone

from plane.db.models import (
    Cycle,
    CycleIssue,
    IntakeIssue,
    Issue,
    IssueAssignee,
    IssueLabel,
    IssueMention,
    IssueMilestone,
    IssueRelation,
    IssueSubscriber,
    ModuleIssue,
    ProjectMember,
    WorkspaceMember,
)

MAX_CONDITIONS = 25

PRIORITIES = ("urgent", "high", "medium", "low", "none")
STATE_GROUPS = ("backlog", "unstarted", "started", "completed", "cancelled", "triage")
OPEN_STATES = ["backlog", "unstarted", "started"]
CLOSED_STATES = ["completed", "cancelled"]
ACTIVE_STATES = ["unstarted", "started"]


class PQLError(ValueError):
    """A PQL string that does not parse or cannot be evaluated."""


# ---------------------------------------------------------------------------
# Tokenizer
# ---------------------------------------------------------------------------

KEYWORDS = {"AND", "OR", "NOT", "IN", "IS", "NULL", "EMPTY", "BETWEEN", "TRUE", "FALSE"}

TOKEN_RE = re.compile(
    r"""
    (?P<ws>\s+)
  | (?P<string>"(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*')
  | (?P<number>-?\d+(?:\.\d+)?)
  | (?P<op>!=|>=|<=|=|>|<|~|!~)
  | (?P<punct>[(),\[\]])
  | (?P<ident>[A-Za-z_][A-Za-z0-9_]*)
    """,
    re.VERBOSE,
)


@dataclass
class Token:
    kind: str  # string | number | op | punct | ident | keyword | end
    value: object
    pos: int


def tokenize(text):
    tokens = []
    pos = 0
    while pos < len(text):
        match = TOKEN_RE.match(text, pos)
        if not match:
            raise PQLError(f"Unexpected character {text[pos]!r} at position {pos}")
        kind = match.lastgroup
        raw = match.group()
        if kind == "string":
            body = raw[1:-1]
            tokens.append(Token("string", re.sub(r"\\(.)", r"\1", body), pos))
        elif kind == "number":
            tokens.append(Token("number", float(raw) if "." in raw else int(raw), pos))
        elif kind == "ident":
            upper = raw.upper()
            tokens.append(Token("keyword", upper, pos) if upper in KEYWORDS else Token("ident", raw, pos))
        elif kind != "ws":
            tokens.append(Token(kind, raw, pos))
        pos = match.end()
    tokens.append(Token("end", None, len(text)))
    return tokens


# ---------------------------------------------------------------------------
# Evaluation context
# ---------------------------------------------------------------------------


class Context:
    def __init__(self, slug, user, project_id=None):
        self.slug = slug
        self.user = user
        self.project_id = project_id
        self.conditions = 0
        # Which of "draft" / "archived" the query asks about. The default
        # issue manager hides both, so the caller widens its base queryset.
        self.hidden = set()
        tz_name = getattr(user, "user_timezone", None) or "UTC"
        try:
            self.tz = pytz.timezone(tz_name)
        except pytz.UnknownTimeZoneError:
            self.tz = pytz.UTC

    def now(self):
        return timezone.now().astimezone(self.tz)

    def today(self):
        return self.now().date()

    def resolve_work_item(self, ref):
        """A work item by UUID or `PROJ-12` identifier, within the workspace."""
        ref = str(ref).strip()
        issues = Issue.objects.filter(workspace__slug=self.slug)
        if _is_uuid(ref):
            issue = issues.filter(pk=ref).first()
        else:
            head, _, seq = ref.rpartition("-")
            if not head or not seq.isdigit():
                raise PQLError(f'Work item reference "{ref}" must be a UUID or an identifier like "WEB-12"')
            issue = issues.filter(project__identifier__iexact=head, sequence_id=int(seq)).first()
        if issue is None:
            raise PQLError(f'Work item "{ref}" was not found in this workspace')
        return issue


def _is_uuid(value):
    try:
        uuid.UUID(str(value))
        return True
    except (ValueError, TypeError):
        return False


# ---------------------------------------------------------------------------
# Value functions — return a scalar or a list
# ---------------------------------------------------------------------------


def _date_functions():
    def week_start(ctx):
        today = ctx.today()
        return today - timedelta(days=today.weekday())

    return {
        "today": (0, lambda ctx: ctx.today()),
        "now": (0, lambda ctx: ctx.now()),
        "startofday": (0, lambda ctx: ctx.today()),
        "endofday": (0, lambda ctx: ctx.today()),
        "startofweek": (0, week_start),
        "endofweek": (0, lambda ctx: week_start(ctx) + timedelta(days=6)),
        "startofmonth": (0, lambda ctx: ctx.today().replace(day=1)),
        "endofmonth": (0, lambda ctx: ctx.today().replace(day=1) + relativedelta(months=1, days=-1)),
        "startofyear": (0, lambda ctx: ctx.today().replace(month=1, day=1)),
        "endofyear": (0, lambda ctx: ctx.today().replace(month=12, day=31)),
        "daysago": (1, lambda ctx, n: ctx.today() - timedelta(days=_int(n))),
        "daysfromnow": (1, lambda ctx, n: ctx.today() + timedelta(days=_int(n))),
        "weeksago": (1, lambda ctx, n: ctx.today() - timedelta(weeks=_int(n))),
        "weeksfromnow": (1, lambda ctx, n: ctx.today() + timedelta(weeks=_int(n))),
        "monthsago": (1, lambda ctx, n: ctx.today() - relativedelta(months=_int(n))),
        "monthsfromnow": (1, lambda ctx, n: ctx.today() + relativedelta(months=_int(n))),
    }


def _int(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise PQLError(f"Expected a number, got {value!r}")
    return int(value)


def _cycles(ctx):
    cycles = Cycle.objects.filter(workspace__slug=ctx.slug, archived_at__isnull=True)
    return cycles.filter(project_id=ctx.project_id) if ctx.project_id else cycles


def _members_of(ctx, ref):
    ref = str(ref)
    project_id = ref.split(":", 1)[1] if ref.lower().startswith("project:") else ref
    if not _is_uuid(project_id):
        raise PQLError('membersOf() takes "project:<project uuid>"')
    return [
        str(m)
        for m in ProjectMember.objects.filter(
            workspace__slug=ctx.slug, project_id=project_id, is_active=True
        ).values_list("member_id", flat=True)
    ]


VALUE_FUNCTIONS = {
    **_date_functions(),
    "currentuser": (0, lambda ctx: str(ctx.user.id)),
    "membersof": (1, _members_of),
    "workspacemembers": (
        0,
        lambda ctx: [
            str(m)
            for m in WorkspaceMember.objects.filter(workspace__slug=ctx.slug, is_active=True).values_list(
                "member_id", flat=True
            )
        ],
    ),
    "activecycle": (
        0,
        lambda ctx: [
            str(c)
            for c in _cycles(ctx)
            .filter(start_date__lte=timezone.now(), end_date__gte=timezone.now())
            .values_list("id", flat=True)
        ],
    ),
    "completedcycles": (
        0,
        lambda ctx: [str(c) for c in _cycles(ctx).filter(end_date__lt=timezone.now()).values_list("id", flat=True)],
    ),
    "upcomingcycles": (
        0,
        lambda ctx: [str(c) for c in _cycles(ctx).filter(start_date__gt=timezone.now()).values_list("id", flat=True)],
    ),
    "openstates": (0, lambda ctx: list(OPEN_STATES)),
    "closedstates": (0, lambda ctx: list(CLOSED_STATES)),
    "activestates": (0, lambda ctx: list(ACTIVE_STATES)),
}


# ---------------------------------------------------------------------------
# Predicate and relation functions — return a Q
# ---------------------------------------------------------------------------


def _live(model, **kwargs):
    return model.objects.filter(deleted_at__isnull=True, **kwargs)


def _relation_ids(issue, relation_type, forward):
    """Issues on the other side of `issue` for one stored relation type.

    A row (issue=A, related_issue=B, relation_type="blocked_by") means A is
    blocked by B. `forward` asks for rows where `issue` is the `related_issue`.
    """
    if forward:
        return _live(IssueRelation, related_issue=issue, relation_type=relation_type).values("issue_id")
    return _live(IssueRelation, issue=issue, relation_type=relation_type).values("related_issue_id")


def _symmetric(issue, relation_type):
    return Q(id__in=_relation_ids(issue, relation_type, True)) | Q(id__in=_relation_ids(issue, relation_type, False))


def _hidden(ctx, kind, q):
    ctx.hidden.add(kind)
    return q


PREDICATES = {
    "isoverdue": lambda ctx: Q(target_date__lt=ctx.today()) & ~Q(state__group__in=CLOSED_STATES),
    "hasnoassignee": lambda ctx: ~Q(id__in=_live(IssueAssignee).values("issue_id")),
    "hasnolabel": lambda ctx: ~Q(id__in=_live(IssueLabel).values("issue_id")),
    "istoplevel": lambda ctx: Q(parent__isnull=True),
    "issubworkitem": lambda ctx: Q(parent__isnull=False),
    "isepic": lambda ctx: Q(type__is_epic=True),
    "haschildren": lambda ctx: Q(Exists(Issue.issue_objects.filter(parent=OuterRef("id")))),
    "hasstartandduedates": lambda ctx: Q(start_date__isnull=False, target_date__isnull=False),
    "isdraft": lambda ctx: _hidden(ctx, "draft", Q(is_draft=True)),
    "isarchived": lambda ctx: _hidden(ctx, "archived", Q(archived_at__isnull=False)),
    "isintake": lambda ctx: Q(id__in=_live(IntakeIssue).values("issue_id")),
}

RELATIONS = {
    "childof": lambda ctx, item: Q(parent_id=item.id),
    "parentof": lambda ctx, item: Q(id=item.parent_id) if item.parent_id else Q(pk__in=[]),
    "linkedto": lambda ctx, item: _symmetric(item, "relates_to"),
    "blockedby": lambda ctx, item: Q(id__in=_relation_ids(item, "blocked_by", True)),
    "blocks": lambda ctx, item: Q(id__in=_relation_ids(item, "blocked_by", False)),
    "duplicateof": lambda ctx, item: _symmetric(item, "duplicate"),
}


# ---------------------------------------------------------------------------
# Fields
# ---------------------------------------------------------------------------


class Field:
    """How one PQL field turns (operator, value) into a Q."""

    kind = "scalar"

    def __init__(self, column, choices=None):
        self.column = column
        self.choices = choices

    def check(self, name, value):
        values = value if isinstance(value, list) else [value]
        for v in values:
            if v is None:
                continue
            if self.choices and str(v).lower() not in self.choices:
                raise PQLError(f"{name} must be one of {', '.join(self.choices)}; got {v!r}")
        if self.choices:
            return [str(v).lower() for v in value] if isinstance(value, list) else str(value).lower()
        return value

    def compare(self, ctx, name, op, value):
        value = self.check(name, value)
        col = self.column
        if op == "=":
            return Q(**{col: value})
        if op == "!=":
            return ~Q(**{col: value})
        if op == "in":
            return Q(**{f"{col}__in": value})
        if op == "~":
            return Q(**{f"{col}__icontains": value})
        if op == "!~":
            return ~Q(**{f"{col}__icontains": value})
        if op == "null":
            return Q(**{f"{col}__isnull": True})
        raise PQLError(f"Operator {op} is not supported on {name}")


class UUIDField(Field):
    def check(self, name, value):
        for v in value if isinstance(value, list) else [value]:
            if not _is_uuid(v):
                raise PQLError(
                    f"{name} needs a UUID, got {v!r}. Look the id up first (list the members/states/labels/...)"
                )
        return value

    def compare(self, ctx, name, op, value):
        if op in ("~", "!~", "<", ">", "<=", ">="):
            raise PQLError(f"Operator {op} is not supported on {name}")
        return super().compare(ctx, name, op, value)


class RelatedField(UUIDField):
    """A many-valued field stored in a join table with soft deletes."""

    def __init__(self, model, column):
        super().__init__(column)
        self.model = model

    def _rows(self, **kwargs):
        return Q(id__in=_live(self.model, **kwargs).values("issue_id"))

    def compare(self, ctx, name, op, value):
        if op == "null":
            return ~self._rows()
        if op in ("=", "!=", "in"):
            value = self.check(name, value)
            lookup = self.column if op != "in" else f"{self.column}__in"
            rows = self._rows(**{lookup: value})
            return ~rows if op == "!=" else rows
        raise PQLError(f"Operator {op} is not supported on {name}")


class DateField(Field):
    def __init__(self, column, is_datetime=False):
        super().__init__(column)
        self.is_datetime = is_datetime

    def coerce(self, name, value):
        if isinstance(value, datetime):
            return value
        if isinstance(value, date):
            return value
        if isinstance(value, str):
            try:
                if "T" in value or " " in value.strip():
                    return datetime.fromisoformat(value.replace("Z", "+00:00"))
                return date.fromisoformat(value)
            except ValueError:
                pass
        raise PQLError(f'{name} needs a date like "2026-10-16" or a date function like today(); got {value!r}')

    def compare(self, ctx, name, op, value):
        if op == "null":
            return Q(**{f"{self.column}__isnull": True})
        if op in ("~", "!~"):
            raise PQLError(f"Operator {op} is not supported on {name}")
        if op == "in":
            raise PQLError(f"IN is not supported on {name}; use BETWEEN or comparisons")
        value = self.coerce(name, value)
        col = self.column
        if isinstance(value, datetime):
            if not self.is_datetime:
                value = value.date()
        elif self.is_datetime:
            col = f"{col}__date"
        lookups = {"=": "", ">": "__gt", ">=": "__gte", "<": "__lt", "<=": "__lte"}
        if op == "!=":
            return ~Q(**{col: value})
        return Q(**{f"{col}{lookups[op]}": value})


class BoolField(Field):
    def __init__(self, kind, to_q):
        super().__init__(None)
        self.kind = kind
        self.to_q = to_q

    def compare(self, ctx, name, op, value):
        if op not in ("=", "!=") or not isinstance(value, bool):
            raise PQLError(f"{name} takes = true or = false")
        ctx.hidden.add(self.kind)
        q = self.to_q(value)
        return ~q if op == "!=" else q


class TextField(Field):
    def __init__(self, columns):
        super().__init__(columns[0])
        self.columns = columns

    def compare(self, ctx, name, op, value):
        if op in ("~", "!~"):
            q = Q()
            for col in self.columns:
                q |= Q(**{f"{col}__icontains": value})
            return ~q if op == "!~" else q
        if op in ("=", "!="):
            q = Q(**{f"{self.column}__iexact": value})
            return ~q if op == "!=" else q
        if op == "null":
            return Q(**{f"{self.column}__isnull": True}) | Q(**{self.column: ""})
        raise PQLError(f"Operator {op} is not supported on {name}")


class IdentifierField(Field):
    def __init__(self):
        super().__init__("id")

    def one(self, ctx, value):
        value = str(value)
        if _is_uuid(value):
            return Q(id=value)
        head, _, seq = value.rpartition("-")
        if not head or not seq.isdigit():
            raise PQLError(f'id must look like "WEB-12" or be a UUID; got {value!r}')
        return Q(project__identifier__iexact=head, sequence_id=int(seq))

    def compare(self, ctx, name, op, value):
        if op == "~":
            value = str(value).rstrip("-")
            head, _, seq = value.rpartition("-")
            if head and seq.isdigit():
                return Q(project__identifier__iexact=head, sequence_id__startswith=seq)
            return Q(project__identifier__istartswith=value)
        if op in ("=", "!="):
            q = self.one(ctx, value)
            return ~q if op == "!=" else q
        if op == "in":
            q = Q(pk__in=[])
            for v in value:
                q |= self.one(ctx, v)
            return q
        raise PQLError(f"Operator {op} is not supported on {name}")


FIELDS = {
    "priority": Field("priority", choices=PRIORITIES),
    "stategroup": Field("state__group", choices=STATE_GROUPS),
    "title": TextField(["name"]),
    "name": TextField(["name"]),
    "text": TextField(["name", "description_stripped"]),
    "id": IdentifierField(),
    "duedate": DateField("target_date"),
    "targetdate": DateField("target_date"),
    "startdate": DateField("start_date"),
    "createdat": DateField("created_at", is_datetime=True),
    "updatedat": DateField("updated_at", is_datetime=True),
    "completedat": DateField("completed_at", is_datetime=True),
    "assignee": RelatedField(IssueAssignee, "assignee_id"),
    "label": RelatedField(IssueLabel, "label_id"),
    "cycle": RelatedField(CycleIssue, "cycle_id"),
    "module": RelatedField(ModuleIssue, "module_id"),
    "milestone": RelatedField(IssueMilestone, "milestone_id"),
    "mention": RelatedField(IssueMention, "mention_id"),
    "subscriber": RelatedField(IssueSubscriber, "subscriber_id"),
    "state": UUIDField("state_id"),
    "project": UUIDField("project_id"),
    "createdby": UUIDField("created_by_id"),
    "type": UUIDField("type_id"),
    "parent": UUIDField("parent_id"),
    "isdraft": BoolField("draft", lambda v: Q(is_draft=v)),
    "isarchived": BoolField("archived", lambda v: Q(archived_at__isnull=not v)),
}

UNSUPPORTED_FIELDS = {
    "teamspaceproject": "Teamspaces are not available on this Plane edition.",
}

FIELD_NAMES = "priority, stateGroup, title, text, id, dueDate, startDate, createdAt, updatedAt, assignee, label, cycle, module, milestone, mention, subscriber, state, project, createdBy, type, parent, isDraft, isArchived"  # noqa: E501


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------


class Parser:
    def __init__(self, text, ctx):
        self.text = text
        self.tokens = tokenize(text)
        self.i = 0
        self.ctx = ctx

    # -- token helpers --------------------------------------------------
    @property
    def tok(self):
        return self.tokens[self.i]

    def advance(self):
        tok = self.tokens[self.i]
        self.i += 1
        return tok

    def at_keyword(self, *words):
        return self.tok.kind == "keyword" and self.tok.value in words

    def at_punct(self, char):
        return self.tok.kind == "punct" and self.tok.value == char

    def expect_punct(self, char):
        if not self.at_punct(char):
            self.fail(f"Expected '{char}'")
        return self.advance()

    def expect_keyword(self, word):
        if not self.at_keyword(word):
            self.fail(f"Expected {word}")
        return self.advance()

    def fail(self, message):
        tok = self.tok
        found = "end of query" if tok.kind == "end" else repr(tok.value)
        raise PQLError(f"{message} at position {tok.pos} (found {found})")

    def count(self):
        self.ctx.conditions += 1
        if self.ctx.conditions > MAX_CONDITIONS:
            raise PQLError(f"Too many conditions; the limit is {MAX_CONDITIONS}")

    # -- grammar --------------------------------------------------------
    def parse(self):
        if self.tok.kind == "end":
            raise PQLError("Empty PQL query")
        q = self.parse_or()
        if self.tok.kind != "end":
            self.fail("Unexpected token")
        return q

    def parse_or(self):
        q = self.parse_and()
        while self.at_keyword("OR"):
            self.advance()
            q = q | self.parse_and()
        return q

    def parse_and(self):
        q = self.parse_not()
        while self.at_keyword("AND"):
            self.advance()
            q = q & self.parse_not()
        return q

    def parse_not(self):
        if self.at_keyword("NOT"):
            self.advance()
            return ~self.parse_not()
        if self.at_punct("("):
            self.advance()
            q = self.parse_or()
            self.expect_punct(")")
            return q
        return self.parse_condition()

    def parse_condition(self):
        tok = self.tok
        if tok.kind != "ident":
            self.fail("Expected a field, predicate or relation function")
        name = tok.value
        key = name.lower()

        # cf["<uuid>"] custom properties
        if key == "cf" and self.tokens[self.i + 1].kind == "punct" and self.tokens[self.i + 1].value == "[":
            raise PQLError("Custom properties (cf[...]) are not available on this Plane edition.")

        # predicate() or relation("X") used standalone
        if self.tokens[self.i + 1].kind == "punct" and self.tokens[self.i + 1].value == "(":
            if key in PREDICATES:
                self.advance()
                self.expect_punct("(")
                self.expect_punct(")")
                self.count()
                return PREDICATES[key](self.ctx)
            if key in RELATIONS:
                self.advance()
                self.expect_punct("(")
                arg = self.parse_value()
                self.expect_punct(")")
                self.count()
                return RELATIONS[key](self.ctx, self.ctx.resolve_work_item(arg))
            if key in VALUE_FUNCTIONS:
                self.fail(f"{name}() is a value, not a condition — compare a field to it")
            self.fail(f"Unknown function {name}()")

        if key in UNSUPPORTED_FIELDS:
            raise PQLError(UNSUPPORTED_FIELDS[key])
        field = FIELDS.get(key)
        if field is None:
            raise PQLError(f"Unknown field {name!r}. Fields: {FIELD_NAMES}")
        self.advance()
        self.count()
        return self.parse_comparison(name, field)

    def parse_comparison(self, name, field):
        ctx = self.ctx
        if self.at_keyword("IS"):
            self.advance()
            negate = False
            if self.at_keyword("NOT"):
                self.advance()
                negate = True
            if not self.at_keyword("NULL", "EMPTY"):
                self.fail("Expected NULL or EMPTY")
            self.advance()
            q = field.compare(ctx, name, "null", None)
            return ~q if negate else q

        negate = False
        if self.at_keyword("NOT"):
            self.advance()
            negate = True
            if not self.at_keyword("IN"):
                self.fail("Expected IN after NOT")

        if self.at_keyword("IN"):
            self.advance()
            values = self.parse_list()
            q = field.compare(ctx, name, "in", values)
            return ~q if negate else q

        if self.at_keyword("BETWEEN"):
            self.advance()
            if self.at_punct("("):
                self.advance()
                low = self.parse_value()
                self.expect_punct(",")
                high = self.parse_value()
                self.expect_punct(")")
            else:
                low = self.parse_value()
                self.expect_keyword("AND")
                high = self.parse_value()
            return field.compare(ctx, name, ">=", low) & field.compare(ctx, name, "<=", high)

        if self.tok.kind != "op":
            self.fail(f"Expected an operator after {name}")
        op = self.advance().value
        value = self.parse_value()
        if isinstance(value, list):
            # `field = listFunction()` reads as membership
            if op == "=":
                return field.compare(ctx, name, "in", value)
            if op == "!=":
                return ~field.compare(ctx, name, "in", value)
            raise PQLError(f"{name} {op} needs a single value, not a list")
        if value is None:
            q = field.compare(ctx, name, "null", None)
            return ~q if op == "!=" else q
        return field.compare(ctx, name, op, value)

    def parse_list(self):
        if self.tok.kind == "ident":
            value = self.parse_value()
            if not isinstance(value, list):
                self.fail("Expected a list")
            return value
        self.expect_punct("(")
        values = []
        while True:
            value = self.parse_value()
            if isinstance(value, list):
                values.extend(value)
            else:
                values.append(value)
            if self.at_punct(","):
                self.advance()
                continue
            break
        self.expect_punct(")")
        return values

    def parse_value(self):
        tok = self.tok
        if tok.kind in ("string", "number"):
            self.advance()
            return tok.value
        if tok.kind == "keyword" and tok.value in ("TRUE", "FALSE"):
            self.advance()
            return tok.value == "TRUE"
        if tok.kind == "keyword" and tok.value == "NULL":
            self.advance()
            return None
        if tok.kind == "punct" and tok.value == "(":
            return self.parse_list()
        if tok.kind == "ident":
            key = tok.value.lower()
            if key not in VALUE_FUNCTIONS:
                self.fail(f"Unknown value function {tok.value}() (strings need double quotes)")
            self.advance()
            arity, fn = VALUE_FUNCTIONS[key]
            self.expect_punct("(")
            args = []
            if not self.at_punct(")"):
                args.append(self.parse_value())
                while self.at_punct(","):
                    self.advance()
                    args.append(self.parse_value())
            self.expect_punct(")")
            if len(args) != arity:
                raise PQLError(f"{tok.value}() takes {arity} argument(s), got {len(args)}")
            return fn(self.ctx, *args)
        self.fail("Expected a value")


def compile_pql(text, slug, user, project_id=None):
    """Compile PQL to (Q, hidden). Raises PQLError on bad input.

    `hidden` names the default-hidden kinds ("draft", "archived") the query
    asks about; see `work_item_base_queryset`.
    """
    ctx = Context(slug, user, project_id)
    q = Parser(text, ctx).parse()
    return q, ctx.hidden


def work_item_base_queryset(hidden=frozenset()):
    """Issue.issue_objects, minus the hiding of the kinds in `hidden`."""
    if not hidden:
        return Issue.issue_objects.all()
    qs = Issue.objects.exclude(state__group="triage").exclude(project__archived_at__isnull=False)
    if "draft" not in hidden:
        qs = qs.exclude(is_draft=True)
    if "archived" not in hidden:
        qs = qs.exclude(archived_at__isnull=False)
    return qs
