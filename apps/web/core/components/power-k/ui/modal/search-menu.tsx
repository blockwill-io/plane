/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useState, useEffect } from "react";
import { useParams } from "next/navigation";
// plane imports
import { WORKSPACE_DEFAULT_SEARCH_RESULT } from "@plane/constants";
import type { IWorkspaceSearchResults } from "@plane/types";
import { Loader } from "@plane/ui";
import { cn } from "@plane/utils";
// hooks
import { usePowerK } from "@/hooks/store/use-power-k";
import useDebounce from "@/hooks/use-debounce";
import { WorkspaceService } from "@/services/workspace.service";
// local imports
import type { TPowerKContext, TPowerKPageType } from "../../core/types";
import { PowerKModalNoSearchResultsCommand } from "./no-results-command";
import { PowerKModalSearchResults } from "./search-results";
// services init
const workspaceService = new WorkspaceService();

type Props = {
  activePage: TPowerKPageType | null;
  context: TPowerKContext;
  isWorkspaceLevel: boolean;
  searchTerm: string;
  updateSearchTerm: (value: string) => void;
  handleSearchMenuClose?: () => void;
};

export function PowerKModalSearchMenu(props: Props) {
  const { activePage, context, isWorkspaceLevel, searchTerm, updateSearchTerm, handleSearchMenuClose } = props;
  // states
  const [resultsCount, setResultsCount] = useState(0);
  const [isSearching, setIsSearching] = useState(false);
  const [results, setResults] = useState<IWorkspaceSearchResults>(WORKSPACE_DEFAULT_SEARCH_RESULT);
  const debouncedSearchTerm = useDebounce(searchTerm, 500);
  // navigation
  const { workspaceSlug, projectId } = useParams();
  // store hooks
  const { togglePowerKModal } = usePowerK();
  // `isSearching` only covers the request itself, and the request is debounced,
  // so it stays false for the first 500ms after a keystroke. Treating the
  // debounce gap as loading too means the skeleton appears the moment typing
  // changes the query, rather than the stale result set sitting there.
  const isAwaitingResults = isSearching || searchTerm.trim() !== debouncedSearchTerm.trim();

  useEffect(() => {
    if (activePage || !workspaceSlug) return;
    setIsSearching(true);

    if (debouncedSearchTerm) {
      workspaceService
        .searchWorkspace(workspaceSlug.toString(), {
          ...(projectId ? { project_id: projectId.toString() } : {}),
          search: debouncedSearchTerm,
          workspace_search: !projectId ? true : isWorkspaceLevel,
        })
        // oxlint-disable-next-line no-shadow oxlint-disable-next-line promise/always-return
        .then((results) => {
          setResults(results);
          const count = Object.keys(results.results).reduce(
            (accumulator, key) => results.results[key as keyof typeof results.results]?.length + accumulator,
            0
          );
          setResultsCount(count);
        })
        .catch(() => {
          setResults(WORKSPACE_DEFAULT_SEARCH_RESULT);
          setResultsCount(0);
        })
        .finally(() => setIsSearching(false));
    } else {
      setResults(WORKSPACE_DEFAULT_SEARCH_RESULT);
      setIsSearching(false);
    }
  }, [debouncedSearchTerm, isWorkspaceLevel, projectId, workspaceSlug, activePage]);

  if (activePage) return null;

  const handleClosePalette = () => {
    handleSearchMenuClose?.();
    togglePowerKModal(false);
  };

  return (
    <>
      {searchTerm.trim() !== "" && (
        <div className="mt-4 flex items-center justify-between gap-2 px-4">
          <h5
            className={cn("text-11 text-primary", {
              "animate-pulse": isAwaitingResults,
            })}
          >
            Search results for{" "}
            <span className="font-medium">
              {'"'}
              {searchTerm}
              {'"'}
            </span>{" "}
            in {isWorkspaceLevel ? "workspace" : "project"}:
          </h5>
        </div>
      )}

      {/* Show empty state only when not loading and no results */}
      {!isAwaitingResults && resultsCount === 0 && searchTerm.trim() !== "" && debouncedSearchTerm.trim() !== "" && (
        <PowerKModalNoSearchResultsCommand
          context={context}
          searchTerm={searchTerm}
          updateSearchTerm={updateSearchTerm}
        />
      )}

      {searchTerm.trim() !== "" &&
        (isAwaitingResults ? (
          // Without this the previous result set — or nothing at all on the
          // first search — sat under the heading until the response landed,
          // which read as "no matches" rather than "still looking".
          <div className="flex flex-col gap-1 px-4 py-2" aria-busy="true" aria-live="polite">
            <span className="sr-only">Searching</span>
            <Loader className="flex flex-col gap-1">
              <Loader.Item height="28px" />
              <Loader.Item height="28px" />
              <Loader.Item height="28px" />
              <Loader.Item height="28px" />
            </Loader>
          </div>
        ) : (
          <PowerKModalSearchResults closePalette={handleClosePalette} results={results} />
        ))}
    </>
  );
}
