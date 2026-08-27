from __future__ import annotations

import os
import subprocess
import textwrap
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TSX = ROOT / "node_modules" / ".bin" / ("tsx.cmd" if os.name == "nt" else "tsx")


def _run_typescript(script: str) -> None:
    wrapped = f"""
    (async () => {{
    {textwrap.dedent(script)}
    }})().catch((error) => {{
      console.error(error);
      process.exitCode = 1;
    }});
    """
    completed = subprocess.run(
        [str(TSX), "-"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        input=textwrap.dedent(wrapped),
        timeout=30,
        check=False,
    )
    assert completed.returncode == 0, (
        f"TypeScript runtime assertion failed ({completed.returncode})\n"
        f"stdout:\n{completed.stdout}\n"
        f"stderr:\n{completed.stderr}"
    )


def test_publication_projection_is_authoritative_for_current_serving_state() -> None:
    _run_typescript(
        """
        const assert = (await import("node:assert/strict")).default;
        const imported = await import("./client/src/lib/ready-data-ui-state.ts");
        const {
          isReadyDataAutomationBusy,
          readyDataOperationKindTranslationKey,
          resolveReadyDataOperationState,
          resolveReadyDataServingState,
        } = imported.default || imported;

        const operationFailedAfterActivePublish = {
          kb_id: "kb-serving",
          profile: "general",
          status: "stale",
          usable: false,
          serving_stale: true,
          stale_reason: "ready_data operation failed",
          error_message: "ready_data operation failed",
          automation_state: "failed",
          last_error: "ready_data operation failed",
          latest_operation_kind: "publish",
          latest_operation_state: "succeeded",
          latest_operation_error: "",
          publication_state: {
            serving_status: "ready",
            serving_usable: true,
            serving_stale: false,
            active_publication_id: "pub-active",
            previous_publication_id: "pub-previous",
            active_publication: { publication_id: "pub-active", status: "active" },
            previous_publication: { publication_id: "pub-previous", status: "previous" },
            latest_operation_kind: "publish",
            latest_operation_state: "succeeded",
            latest_operation_error: "",
          },
        };
        assert.deepEqual(resolveReadyDataServingState(operationFailedAfterActivePublish), {
          status: "ready",
          usable: true,
          stale: false,
          source: "publication_state",
        });
        assert.deepEqual(resolveReadyDataOperationState(operationFailedAfterActivePublish), {
          kind: "publish",
          status: "succeeded",
          error: "",
          at: null,
          source: "publication_state",
        });

        const failedAutomation = {
          ...operationFailedAfterActivePublish,
          latest_operation_kind: "automation",
          latest_operation_state: "failed",
          latest_operation_error: "ready_data operation failed",
          publication_state: {
            ...operationFailedAfterActivePublish.publication_state,
            latest_operation_kind: "automation",
            latest_operation_state: "failed",
            latest_operation_error: "ready_data operation failed",
          },
        };
        assert.deepEqual(resolveReadyDataOperationState(failedAutomation), {
          kind: "automation",
          status: "failed",
          error: "ready_data operation failed",
          at: null,
          source: "publication_state",
        });

        assert.equal(isReadyDataAutomationBusy("pending"), true);
        assert.equal(isReadyDataAutomationBusy("running"), true);
        assert.equal(isReadyDataAutomationBusy("building"), true);
        assert.equal(isReadyDataAutomationBusy("failed"), false);
        assert.equal(isReadyDataAutomationBusy("succeeded"), false);
        assert.equal(readyDataOperationKindTranslationKey("build"), "knowledge.ready_operation_build");
        assert.equal(readyDataOperationKindTranslationKey("publish"), "knowledge.ready_operation_publish");
        assert.equal(readyDataOperationKindTranslationKey("rollback"), "knowledge.ready_operation_rollback");
        assert.equal(readyDataOperationKindTranslationKey("automation"), "knowledge.ready_operation_automation");
        assert.equal(readyDataOperationKindTranslationKey("unexpected"), "knowledge.ready_operation_none");

        const softStaleActive = {
          ...operationFailedAfterActivePublish,
          publication_state: {
            ...operationFailedAfterActivePublish.publication_state,
            serving_status: "stale",
            serving_usable: true,
            serving_stale: true,
          },
        };
        assert.deepEqual(resolveReadyDataServingState(softStaleActive), {
          status: "stale",
          usable: true,
          stale: true,
          source: "publication_state",
        });

        assert.deepEqual(resolveReadyDataServingState({
          kb_id: "legacy-kb",
          profile: "general",
          status: "ready",
          usable: true,
          serving_stale: false,
        }), {
          status: "ready",
          usable: true,
          stale: false,
          source: "legacy_manifest",
        });
        """
    )


def test_delayed_ready_data_mutations_cannot_cross_route_epoch() -> None:
    _run_typescript(
        """
        const assert = (await import("node:assert/strict")).default;
        const imported = await import("./client/src/lib/ready-data-ui-state.ts");
        const {
          captureReadyDataRoute,
          isReadyDataRouteCurrent,
          runReadyDataRouteMutation,
          syncReadyDataRoute,
        } = imported.default || imported;

        const deferred = () => {
          let resolve;
          let reject;
          const promise = new Promise((yes, no) => { resolve = yes; reject = no; });
          return { promise, resolve, reject };
        };

        for (const action of ["build", "automation", "rollback"]) {
          for (const outcome of ["success", "failure"]) {
            let route = { kbId: "A", epoch: 0 };
            let mounted = true;
            const token = captureReadyDataRoute(route, mounted, "A");
            assert.ok(token);
            let view = {
              manifest: "A-start",
              meta: "A-start",
              notice: null,
              error: null,
              loading: true,
              followups: 0,
            };
            const pending = deferred();
            const operation = runReadyDataRouteMutation({
              request: () => pending.promise,
              isCurrent: () => isReadyDataRouteCurrent(route, mounted, token),
              onSuccess: (result) => {
                view.manifest = `${action}-${result}`;
                view.meta = `${action}-${result}`;
                view.notice = `${action}-done`;
                view.followups += 1;
              },
              onError: () => {
                view.error = `${action}-failed`;
                view.followups += 1;
              },
              onSettled: () => { view.loading = false; },
            });

            route = syncReadyDataRoute(route, "B");
            view = {
              manifest: "B-current",
              meta: "B-current",
              notice: "B-notice",
              error: "B-error",
              loading: false,
              followups: 0,
            };
            if (outcome === "success") pending.resolve("response");
            else pending.reject(new Error("delayed A failure"));
            await operation;
            assert.deepEqual(view, {
              manifest: "B-current",
              meta: "B-current",
              notice: "B-notice",
              error: "B-error",
              loading: false,
              followups: 0,
            });
          }
        }

        let strictRoute = { kbId: "A", epoch: 4 };
        let strictMounted = false;
        strictRoute = syncReadyDataRoute(strictRoute, "");
        strictMounted = true;
        strictRoute = syncReadyDataRoute(strictRoute, "A");
        assert.ok(captureReadyDataRoute(strictRoute, strictMounted, "A"));
        """
    )


def test_automation_confirmation_meta_fallback_and_bounded_polling() -> None:
    _run_typescript(
        """
        const assert = (await import("node:assert/strict")).default;
        const imported = await import("./client/src/lib/ready-data-ui-state.ts");
        const {
          mergeConfirmedReadyDataAutomation,
          readyDataManifestAfterLoad,
          scheduleReadyDataPoll,
          selectEffectiveReadyDataManifest,
          shouldPollReadyDataManifest,
        } = imported.default || imported;

        const base = {
          kb_id: "A",
          profile: "general",
          status: "ready",
          usable: true,
          automatic_build_enabled: false,
          automatic_publish_enabled: false,
          automation_state: "idle",
        };
        const confirmed = mergeConfirmedReadyDataAutomation(base, "A", "general", {
          kb_id: "A",
          profile: "general",
          automation: {
            automatic_build_enabled: true,
            automatic_publish_enabled: true,
            automation_state: "running",
            pending_evaluation_generation: 7,
            running_generation: 6,
          },
        });
        assert.equal(confirmed.automatic_build_enabled, true);
        assert.equal(confirmed.automatic_publish_enabled, true);
        assert.equal(confirmed.automation_state, "running");
        assert.equal(confirmed.pending_generation, 7);
        assert.equal(confirmed.running_generation, 6);

        // A failed dedicated GET (for example HTTP 503) retains the confirmed PUT state.
        const after503 = readyDataManifestAfterLoad(confirmed, null, false, true);
        assert.equal(after503, confirmed);
        assert.equal(shouldPollReadyDataManifest(after503, 0, 12), true);
        assert.equal(shouldPollReadyDataManifest(after503, 12, 12), false);

        const succeeded = { ...confirmed, automation_state: "succeeded" };
        let pollManifest = after503;
        let scheduled = null;
        let cleared = null;
        const cancel = scheduleReadyDataPoll(
          () => {
            pollManifest = readyDataManifestAfterLoad(pollManifest, succeeded, true, true);
            scheduled = "ran";
          },
          3000,
          (callback, delay) => { scheduled = { callback, delay }; return 41; },
          (handle) => { cleared = handle; },
        );
        assert.equal(scheduled.delay, 3000);
        const callback = scheduled.callback;
        callback();
        assert.equal(scheduled, "ran");
        cancel();
        assert.equal(cleared, 41);

        assert.equal(pollManifest, succeeded);
        assert.equal(shouldPollReadyDataManifest(pollManifest, 1, 12), false);

        const disabled = mergeConfirmedReadyDataAutomation(confirmed, "A", "general", {
          automation: {
            automatic_build_enabled: false,
            automatic_publish_enabled: true,
            automation_state: "idle",
          },
        });
        assert.equal(disabled.automatic_build_enabled, false);
        assert.equal(disabled.automatic_publish_enabled, false);
        assert.equal(shouldPollReadyDataManifest(disabled, 0, 12), false);

        const metaRunning = { ...base, automation_state: "running" };
        const dedicatedAfter503 = readyDataManifestAfterLoad(null, null, false, true);
        const effectiveMeta = selectEffectiveReadyDataManifest(
          "A",
          dedicatedAfter503,
          "A",
          metaRunning,
        );
        assert.equal(effectiveMeta, metaRunning);
        assert.equal(shouldPollReadyDataManifest(effectiveMeta, 0, 12), true);
        assert.equal(
          selectEffectiveReadyDataManifest("A", null, "A", { ...metaRunning, kb_id: "B" }),
          null,
        );
        assert.equal(selectEffectiveReadyDataManifest("A", null, "B", metaRunning), null);
        assert.equal(
          selectEffectiveReadyDataManifest("A", succeeded, "A", metaRunning),
          succeeded,
        );
        """
    )


def test_poll_cleanup_and_rollback_error_keys_are_executable() -> None:
    _run_typescript(
        """
        const assert = (await import("node:assert/strict")).default;
        const imported = await import("./client/src/lib/ready-data-ui-state.ts");
        const { readyDataRollbackErrorKey, scheduleReadyDataPoll } = imported.default || imported;

        let callback = null;
        let cleared = null;
        const cancel = scheduleReadyDataPoll(
          () => { throw new Error("cancelled timer executed"); },
          3000,
          (next) => { callback = next; return 73; },
          (handle) => { cleared = handle; callback = null; },
        );
        cancel();
        assert.equal(cleared, 73);
        assert.equal(callback, null);

        assert.equal(readyDataRollbackErrorKey(409, true), "knowledge.ready_rollback_conflict");
        assert.equal(
          readyDataRollbackErrorKey(409, false),
          "knowledge.ready_rollback_conflict_refresh_failed",
        );
        assert.equal(readyDataRollbackErrorKey(422, false), "knowledge.ready_rollback_failed");
        assert.equal(readyDataRollbackErrorKey(500, false), "knowledge.ready_rollback_failed");
        """
    )


def test_delayed_detail_loads_and_stale_profile_cannot_cross_kb_route() -> None:
    _run_typescript(
        """
        const assert = (await import("node:assert/strict")).default;
        const imported = await import("./client/src/lib/ready-data-ui-state.ts");
        const {
          captureReadyDataRoute,
          isReadyDataRouteCurrent,
          runReadyDataRouteRequest,
          selectReadyDataMutationProfile,
          syncReadyDataRoute,
        } = imported.default || imported;

        const deferred = () => {
          let resolve;
          let reject;
          const promise = new Promise((yes, no) => { resolve = yes; reject = no; });
          return { promise, resolve, reject };
        };
        const fields = ["meta", "manifest", "stats", "files", "categories", "unmapped"];
        let route = { kbId: "A", epoch: 0 };
        let mounted = true;
        let view = {
          meta: "A-old",
          manifest: "A-old",
          stats: "A-old",
          files: "A-old",
          categories: "A-old",
          unmapped: "A-old",
          editName: "A-old",
          editDesc: "A-old",
          notice: null,
          loading: true,
        };

        const startLoad = (routeKbId, field, pending, failureValue) => {
          const token = captureReadyDataRoute(route, mounted, routeKbId);
          assert.ok(token);
          return runReadyDataRouteRequest({
            request: () => pending.promise,
            isCurrent: () => isReadyDataRouteCurrent(route, mounted, token),
            onSuccess: (value) => {
              view[field] = value;
              if (field === "meta") {
                view.editName = `${value}-name`;
                view.editDesc = `${value}-desc`;
              }
            },
            onError: () => {
              view[field] = failureValue;
              if (field === "meta") {
                view.manifest = failureValue;
              }
            },
          });
        };

        const aPending = Object.fromEntries(fields.map((field) => [field, deferred()]));
        const aLoads = fields.map((field) => startLoad("A", field, aPending[field], `A-${field}-error`));
        const aToken = captureReadyDataRoute(route, mounted, "A");
        const aSettled = runReadyDataRouteRequest({
          request: () => Promise.all(aLoads),
          isCurrent: () => isReadyDataRouteCurrent(route, mounted, aToken),
          onSuccess: () => {},
          onError: () => {},
          onSettled: () => { view.loading = false; },
        });

        route = syncReadyDataRoute(route, "B");
        view = {
          meta: null,
          manifest: null,
          stats: null,
          files: [],
          categories: [],
          unmapped: [],
          editName: "",
          editDesc: "",
          notice: null,
          loading: true,
        };
        assert.equal(
          selectReadyDataMutationProfile("B", null, "A", "special-a"),
          "general",
        );

        const bPending = Object.fromEntries(fields.map((field) => [field, deferred()]));
        const bLoads = fields.map((field) => startLoad("B", field, bPending[field], `B-${field}-error`));
        const bToken = captureReadyDataRoute(route, mounted, "B");
        const bSettled = runReadyDataRouteRequest({
          request: () => Promise.all(bLoads),
          isCurrent: () => isReadyDataRouteCurrent(route, mounted, bToken),
          onSuccess: () => {},
          onError: () => {},
          onSettled: () => { view.loading = false; },
        });
        for (const field of fields) bPending[field].resolve(`B-${field}`);
        await Promise.all([...bLoads, bSettled]);
        view.notice = "B-notice";
        const expectedB = structuredClone(view);

        aPending.meta.resolve("A-meta-late");
        aPending.manifest.reject(new Error("A manifest late failure"));
        aPending.stats.resolve("A-stats-late");
        aPending.files.reject(new Error("A files late failure"));
        aPending.categories.resolve("A-categories-late");
        aPending.unmapped.reject(new Error("A unmapped late failure"));
        await Promise.all([...aLoads, aSettled]);
        assert.deepEqual(view, expectedB);
        assert.equal(
          selectReadyDataMutationProfile("B", { kb_id: "B", profile: "claims-b" }, "A", "special-a"),
          "claims-b",
        );
        assert.equal(
          selectReadyDataMutationProfile("B", null, "B", "stored-b"),
          "stored-b",
        );
        """
    )


def test_latest_same_kb_resource_request_and_load_episode_win() -> None:
    _run_typescript(
        """
        const assert = (await import("node:assert/strict")).default;
        const imported = await import("./client/src/lib/ready-data-ui-state.ts");
        const {
          captureReadyDataRequest,
          isReadyDataRequestCurrent,
          runReadyDataRouteRequest,
          selectReadyDataMutationProfile,
        } = imported.default || imported;

        const deferred = () => {
          let resolve;
          let reject;
          const promise = new Promise((yes, no) => { resolve = yes; reject = no; });
          return { promise, resolve, reject };
        };
        const route = { kbId: "same-kb", epoch: 3 };
        const mounted = true;
        const sequences = {
          meta: 0,
          stats: 0,
          files: 0,
          categories: 0,
          unmapped: 0,
        };
        const view = {
          meta: null,
          stats: null,
          files: null,
          categories: null,
          unmapped: null,
        };

        const startResource = (field, pending) => {
          const requestId = ++sequences[field];
          const token = captureReadyDataRequest(route, mounted, "same-kb", requestId);
          assert.ok(token);
          return runReadyDataRouteRequest({
            request: () => pending.promise,
            isCurrent: () => isReadyDataRequestCurrent(
              route,
              mounted,
              token,
              sequences[field],
            ),
            onSuccess: (value) => { view[field] = value; },
            onError: () => { view[field] = `${field}-error`; },
          });
        };

        for (const field of Object.keys(sequences)) {
          const oldSuccess = deferred();
          const newSuccess = deferred();
          const oldSuccessRun = startResource(field, oldSuccess);
          const newSuccessRun = startResource(field, newSuccess);
          const newValue = field === "meta"
            ? {
                kb_id: "same-kb",
                manifest_profile: "new-profile",
                agentic_ready_manifest: {
                  kb_id: "same-kb",
                  profile: "new-profile",
                  status: "ready",
                  usable: true,
                },
              }
            : `${field}-new`;
          newSuccess.resolve(newValue);
          await newSuccessRun;
          oldSuccess.resolve(`${field}-old`);
          await oldSuccessRun;
          assert.deepEqual(view[field], newValue);

          const oldError = deferred();
          const newestSuccess = deferred();
          const oldErrorRun = startResource(field, oldError);
          const newestSuccessRun = startResource(field, newestSuccess);
          const newestValue = field === "meta"
            ? {
                kb_id: "same-kb",
                manifest_profile: "newest-profile",
                agentic_ready_manifest: {
                  kb_id: "same-kb",
                  profile: "newest-profile",
                  status: "ready",
                  usable: true,
                },
              }
            : `${field}-newest`;
          newestSuccess.resolve(newestValue);
          await newestSuccessRun;
          oldError.reject(new Error(`${field} stale failure`));
          await oldErrorRun;
          assert.deepEqual(view[field], newestValue);
        }

        assert.equal(
          selectReadyDataMutationProfile(
            "same-kb",
            view.meta.agentic_ready_manifest,
            view.meta.kb_id,
            view.meta.manifest_profile,
          ),
          "newest-profile",
        );

        let loadEpisode = 0;
        let loading = false;
        const startLoadEpisode = (pending) => {
          const requestId = ++loadEpisode;
          const token = captureReadyDataRequest(route, mounted, "same-kb", requestId);
          loading = true;
          return runReadyDataRouteRequest({
            request: () => pending.promise,
            isCurrent: () => isReadyDataRequestCurrent(
              route,
              mounted,
              token,
              loadEpisode,
            ),
            onSuccess: () => {},
            onError: () => {},
            onSettled: () => { loading = false; },
          });
        };
        const oldEpisode = deferred();
        const newEpisode = deferred();
        const oldEpisodeRun = startLoadEpisode(oldEpisode);
        const newEpisodeRun = startLoadEpisode(newEpisode);
        oldEpisode.resolve("old-done");
        await oldEpisodeRun;
        assert.equal(loading, true);
        newEpisode.resolve("new-done");
        await newEpisodeRun;
        assert.equal(loading, false);
        """
    )


def test_delayed_automation_confirmation_merges_into_latest_same_kb_manifests() -> None:
    _run_typescript(
        """
        const assert = (await import("node:assert/strict")).default;
        const imported = await import("./client/src/lib/ready-data-ui-state.ts");
        const {
          captureReadyDataRoute,
          isReadyDataRouteCurrent,
          mergeConfirmedReadyDataAutomationForKb,
          readyDataManifestAfterLoad,
          resolveReadyDataManifestEpisode,
          runReadyDataRouteMutation,
          selectReadyDataManifestEpisodeUpdate,
          shouldPollReadyDataManifest,
          syncReadyDataRoute,
        } = imported.default || imported;

        const oldManifest = {
          kb_id: "same-kb",
          profile: "general",
          status: "ready",
          usable: true,
          serving_stale: false,
          stale_severity: "none",
          authoritative_source_version_id: "source-old",
          observed_index_version_id: "index-old",
          artifact_digest: "digest-old",
          publication_state: {
            active_publication_id: "pub-old",
            previous_publication_id: "pub-older",
            active_publication: { publication_id: "pub-old" },
            previous_publication: { publication_id: "pub-older" },
          },
          automation_state: "idle",
          automatic_build_enabled: false,
          automatic_publish_enabled: false,
        };
        const newManifest = {
          ...oldManifest,
          serving_stale: true,
          stale_severity: "soft_stale",
          stale_reasons: ["metadata_updated"],
          authoritative_source_version_id: "source-new",
          observed_index_version_id: "index-new",
          artifact_digest: "digest-new",
          publication_state: {
            active_publication_id: "pub-new",
            previous_publication_id: "pub-old",
            active_publication: { publication_id: "pub-new" },
            previous_publication: { publication_id: "pub-old" },
          },
        };
        const busyResponse = {
          kb_id: "same-kb",
          profile: "general",
          automation: {
            automatic_build_enabled: true,
            automatic_publish_enabled: true,
            automation_state: "running",
            pending_evaluation_generation: 9,
            running_generation: 8,
          },
        };
        const mergedDedicated = mergeConfirmedReadyDataAutomationForKb(
          newManifest,
          oldManifest,
          "same-kb",
          "general",
          busyResponse,
        );
        for (const key of [
          "serving_stale",
          "stale_severity",
          "stale_reasons",
          "authoritative_source_version_id",
          "observed_index_version_id",
          "artifact_digest",
          "publication_state",
        ]) assert.deepEqual(mergedDedicated[key], newManifest[key], key);
        assert.equal(mergedDedicated.automatic_build_enabled, true);
        assert.equal(mergedDedicated.automatic_publish_enabled, true);
        assert.equal(mergedDedicated.automation_state, "running");

        // A newer GET may finish before an older automation PUT. The PUT is
        // stale as a whole-manifest episode, but its confirmed fields are a
        // safe overlay because the candidate was built from the response-time
        // same-profile publication rather than the request-time snapshot.
        const stalePutDecision = resolveReadyDataManifestEpisode(
          "same-kb",
          mergedDedicated,
          1,
          { profile: "general", version: 2 },
        );
        assert.equal(stalePutDecision.authoritative, false);
        const confirmedAfterNewerGet = selectReadyDataManifestEpisodeUpdate(
          newManifest,
          mergedDedicated,
          "same-kb",
          stalePutDecision,
          true,
        );
        assert.equal(
          confirmedAfterNewerGet.publication_state.active_publication_id,
          "pub-new",
        );
        assert.equal(confirmedAfterNewerGet.automation_state, "running");
        assert.equal(confirmedAfterNewerGet.automatic_build_enabled, true);

        // The forced GET fails (for example HTTP 503): confirmed automation and
        // the newer publication/provenance both remain, and busy state still polls.
        const after503 = readyDataManifestAfterLoad(
          mergedDedicated,
          null,
          false,
          true,
        );
        assert.equal(after503, mergedDedicated);
        assert.equal(after503.publication_state.active_publication_id, "pub-new");
        assert.equal(shouldPollReadyDataManifest(after503, 0, 12), true);

        const nestedNew = {
          ...newManifest,
          authoritative_source_version_id: "source-meta-new",
          artifact_digest: "digest-meta-new",
          publication_state: {
            active_publication_id: "pub-meta-new",
            previous_publication_id: "pub-new",
          },
        };
        const mergedNested = mergeConfirmedReadyDataAutomationForKb(
          nestedNew,
          oldManifest,
          "same-kb",
          "general",
          busyResponse,
        );
        assert.equal(mergedNested.publication_state.active_publication_id, "pub-meta-new");
        assert.equal(mergedNested.artifact_digest, "digest-meta-new");
        assert.equal(mergedNested.automation_state, "running");

        const idleResponse = {
          automation: {
            automatic_build_enabled: true,
            automatic_publish_enabled: false,
            automation_state: "idle",
          },
        };
        const idleMerged = mergeConfirmedReadyDataAutomationForKb(
          newManifest,
          oldManifest,
          "same-kb",
          "general",
          idleResponse,
        );
        assert.equal(idleMerged.publication_state.active_publication_id, "pub-new");
        assert.equal(idleMerged.artifact_digest, "digest-new");
        assert.equal(shouldPollReadyDataManifest(idleMerged, 0, 12), false);

        const deferred = () => {
          let resolve;
          const promise = new Promise((yes) => { resolve = yes; });
          return { promise, resolve };
        };
        let route = { kbId: "same-kb", epoch: 2 };
        const token = captureReadyDataRoute(route, true, "same-kb");
        let routeWrites = 0;
        const pending = deferred();
        const operation = runReadyDataRouteMutation({
          request: () => pending.promise,
          isCurrent: () => isReadyDataRouteCurrent(route, true, token),
          onSuccess: () => { routeWrites += 1; },
          onError: () => { routeWrites += 1; },
        });
        route = syncReadyDataRoute(route, "other-kb");
        pending.resolve(busyResponse);
        await operation;
        assert.equal(routeWrites, 0);
        """
    )


def test_publication_revision_orders_every_same_kb_manifest_write() -> None:
    _run_typescript(
        """
        const assert = (await import("node:assert/strict")).default;
        const imported = await import("./client/src/lib/ready-data-ui-state.ts");
        const {
          mergeConfirmedReadyDataAutomationForKb,
          selectReadyDataManifestUpdate,
        } = imported.default || imported;

        const manifest = (id, revision, digest = `digest-${id}`) => ({
          kb_id: "same-kb",
          profile: "general",
          status: "ready",
          usable: true,
          publication_revision: revision,
          artifact_digest: digest,
          authoritative_source_version_id: `source-${id}`,
          observed_index_version_id: `index-${id}`,
          serving_stale: id.includes("stale"),
          publication_state: {
            publication_revision: revision,
            active_publication_id: id,
            previous_publication_id: `previous-${id}`,
          },
        });
        const old = manifest("pub-old", 4);
        const newer = manifest("pub-new", 5);
        assert.equal(
          selectReadyDataManifestUpdate(newer, old, "same-kb", false),
          newer,
        );
        assert.equal(
          selectReadyDataManifestUpdate(newer, old, "same-kb", true),
          newer,
        );
        assert.equal(
          selectReadyDataManifestUpdate(old, newer, "same-kb", false),
          newer,
        );

        const equalCurrent = manifest("pub-equal-current", 5, "digest-current");
        const equalIncoming = manifest("pub-equal-incoming", 5, "digest-incoming");
        assert.equal(
          selectReadyDataManifestUpdate(
            equalCurrent,
            equalIncoming,
            "same-kb",
            false,
          ),
          equalCurrent,
        );
        assert.equal(
          selectReadyDataManifestUpdate(
            equalCurrent,
            equalIncoming,
            "same-kb",
            true,
          ),
          equalIncoming,
        );

        // A compact KB-meta fallback can arrive before the complete public GET.
        // Equal pointer revisions must let the authoritative GET fill in the
        // projected active/previous provenance, while a later nested fallback
        // must not downgrade that complete state.
        const nestedFallback = {
          kb_id: "same-kb",
          profile: "general",
          status: "ready",
          usable: true,
          publication_revision: 5,
          artifact_digest: "digest-nested",
        };
        const completeDedicated = manifest("pub-complete", 5, "digest-complete");
        assert.equal(
          selectReadyDataManifestUpdate(
            nestedFallback,
            completeDedicated,
            "same-kb",
            true,
          ),
          completeDedicated,
        );
        assert.equal(
          selectReadyDataManifestUpdate(
            completeDedicated,
            nestedFallback,
            "same-kb",
            true,
          ),
          completeDedicated,
        );

        const legacyCurrent = manifest("legacy-current", null, "legacy-current");
        const legacyIncoming = manifest("legacy-incoming", null, "legacy-incoming");
        assert.equal(
          selectReadyDataManifestUpdate(
            legacyCurrent,
            legacyIncoming,
            "same-kb",
            false,
          ),
          legacyCurrent,
        );
        assert.equal(
          selectReadyDataManifestUpdate(
            legacyCurrent,
            legacyIncoming,
            "same-kb",
            true,
          ),
          legacyIncoming,
        );
        assert.equal(
          selectReadyDataManifestUpdate(newer, legacyIncoming, "same-kb", true),
          newer,
        );
        assert.equal(
          selectReadyDataManifestUpdate(
            newer,
            { ...manifest("wrong", 99), kb_id: "other-kb" },
            "same-kb",
            true,
          ),
          newer,
        );

        const busyResponse = {
          profile: "general",
          automation: {
            automatic_build_enabled: true,
            automatic_publish_enabled: true,
            automation_state: "running",
          },
        };
        const fromNestedOnly = mergeConfirmedReadyDataAutomationForKb(
          null,
          newer,
          "same-kb",
          "general",
          busyResponse,
        );
        assert.equal(fromNestedOnly.publication_state.active_publication_id, "pub-new");
        assert.equal(fromNestedOnly.artifact_digest, "digest-pub-new");
        assert.equal(fromNestedOnly.automation_state, "running");

        const withoutResponseTimePublication = mergeConfirmedReadyDataAutomationForKb(
          null,
          null,
          "same-kb",
          "general",
          busyResponse,
        );
        assert.equal(withoutResponseTimePublication.publication_state, undefined);
        assert.equal(withoutResponseTimePublication.artifact_digest, undefined);
        assert.equal(withoutResponseTimePublication.automation_state, "running");
        """
    )


def test_knowledge_list_and_detail_build_snapshots_reject_stale_publication_writes() -> None:
    _run_typescript(
        """
        const assert = (await import("node:assert/strict")).default;
        const imported = await import("./client/src/lib/ready-data-ui-state.ts");
        const {
          mergeReadyDataKnowledgeList,
          mergeReadyDataKnowledgeManifest,
          readyDataManifestAfterLoad,
          selectReadyDataManifestUpdate,
        } = imported.default || imported;

        const manifest = (kbId, publicationId, revision, automationState) => ({
          kb_id: kbId,
          profile: "general",
          status: "ready",
          usable: true,
          automation_state: automationState,
          publication_revision: revision,
          artifact_digest: `digest-${publicationId}`,
          publication_state: {
            publication_revision: revision,
            active_publication_id: publicationId,
            previous_publication_id: `previous-${publicationId}`,
            active_publication: { publication_id: publicationId },
            previous_publication: { publication_id: `previous-${publicationId}` },
          },
        });
        const deferred = () => {
          let resolve;
          const promise = new Promise((yes) => { resolve = yes; });
          return { promise, resolve };
        };

        const oldListResponse = [
          { id: "B", name: "B-old", agentic_ready_manifest: manifest("B", "pub-b4", 4, "idle") },
          { id: "A", name: "A-old", agentic_ready_manifest: manifest("A", "pub-a4", 4, "idle") },
          { id: "C", name: "C-new", agentic_ready_manifest: manifest("C", "pub-c1", 1, "idle") },
        ];
        let view = [
          { id: "A", name: "A-current", agentic_ready_manifest: manifest("A", "pub-a3", 3, "idle") },
          { id: "B", name: "B-current", agentic_ready_manifest: manifest("B", "pub-b3", 3, "idle") },
          { id: "removed", name: "removed", agentic_ready_manifest: manifest("removed", "pub-r1", 1, "idle") },
        ];

        // The build completes before an older list GET. Membership/order and
        // ordinary fields still come from that GET, but its rev4/idle manifest
        // cannot replace the rev5/running build snapshot.
        const pendingOldList = deferred();
        const pendingBuild = deferred();
        const oldListRun = pendingOldList.promise.then((response) => {
          view = mergeReadyDataKnowledgeList(view, response);
        });
        const buildRun = pendingBuild.promise.then((response) => {
          view = mergeReadyDataKnowledgeManifest(view, "A", response, false);
        });
        pendingBuild.resolve(manifest("A", "pub-a5", 5, "running"));
        await buildRun;
        pendingOldList.resolve(oldListResponse);
        await oldListRun;
        assert.deepEqual(view.map((item) => item.id), ["B", "A", "C"]);
        assert.equal(view.find((item) => item.id === "A").name, "A-old");
        assert.equal(
          view.find((item) => item.id === "A").agentic_ready_manifest.publication_state.active_publication_id,
          "pub-a5",
        );
        assert.equal(view.find((item) => item.id === "A").agentic_ready_manifest.automation_state, "running");
        assert.equal(view.some((item) => item.id === "removed"), false);

        // A newer list GET wins, then a delayed lower-revision build response
        // cannot roll publication or automation state backward.
        const pendingHigherList = deferred();
        const pendingLowerBuild = deferred();
        const higherListRun = pendingHigherList.promise.then((response) => {
          view = mergeReadyDataKnowledgeList(view, response);
        });
        const lowerBuildRun = pendingLowerBuild.promise.then((response) => {
          view = mergeReadyDataKnowledgeManifest(view, "A", response, false);
        });
        pendingHigherList.resolve([
          { id: "A", name: "A-new", agentic_ready_manifest: manifest("A", "pub-a6", 6, "succeeded") },
        ]);
        await higherListRun;
        pendingLowerBuild.resolve(manifest("A", "pub-a5-late", 5, "idle"));
        await lowerBuildRun;
        assert.equal(view.length, 1);
        assert.equal(view[0].agentic_ready_manifest.publication_state.active_publication_id, "pub-a6");
        assert.equal(view[0].agentic_ready_manifest.automation_state, "succeeded");

        // KBDetail consumes the safe full build snapshot. A forced GET failure
        // preserves active/previous/provenance, leaving rollback available.
        const compactBeforeBuild = {
          kb_id: "detail-kb",
          profile: "general",
          status: "ready",
          usable: true,
          publication_revision: 2,
        };
        const fullBuildManifest = manifest("detail-kb", "pub-detail-2", 2, "idle");
        const afterBuild = selectReadyDataManifestUpdate(
          compactBeforeBuild,
          fullBuildManifest,
          "detail-kb",
          false,
        );
        const after503 = readyDataManifestAfterLoad(afterBuild, null, false, true);
        assert.equal(after503.publication_state.active_publication_id, "pub-detail-2");
        assert.equal(after503.publication_state.previous_publication_id, "previous-pub-detail-2");
        assert.ok(after503.publication_state.previous_publication);
        assert.equal(after503.artifact_digest, "digest-pub-detail-2");
        """
    )


def test_same_revision_dynamic_state_and_profile_scoped_list_ordering() -> None:
    _run_typescript(
        """
        const assert = (await import("node:assert/strict")).default;
        const imported = await import("./client/src/lib/ready-data-ui-state.ts");
        const {
          isReadyDataKnowledgeListManifestAuthoritative,
          mergeReadyDataKnowledgeList,
          mergeReadyDataKnowledgeManifest,
          resolveReadyDataOperationState,
          selectReadyDataManifestUpdate,
          selectReadyDataMutationProfile,
          shouldPollReadyDataManifest,
        } = imported.default || imported;

        const full = {
          kb_id: "same-kb",
          profile: "general",
          status: "ready",
          usable: true,
          fallback_mode: "agentic",
          serving_stale: false,
          stale_confirmed: false,
          stale_severity: "none",
          stale_reasons: [],
          source_state: { state: "fresh", serving_allowed: true },
          event_generation: 5,
          pending_evaluation_generation: null,
          evaluated_generation: 5,
          automation_state: "idle",
          automatic_build_enabled: false,
          automatic_publish_enabled: false,
          pending_generation: null,
          running_generation: null,
          last_attempt_publication_id: "attempt-old",
          last_success_at: "2026-08-20T10:00:00Z",
          last_error: null,
          latest_operation_kind: "publish",
          latest_operation_state: "succeeded",
          latest_operation_at: "2026-08-20T10:00:00Z",
          latest_operation_error: "",
          current_ready_index_version_id: "index-current-old",
          smoke_status: "passed",
          smoke_checked_at: "2026-08-20T10:01:00Z",
          publication_revision: 5,
          authoritative_source_version_kind: "catalog_chunks_snapshot",
          authoritative_source_version_id: "source-authoritative",
          observed_index_version_id: "index-observed",
          artifact_digest: "digest-active",
          publication_state: {
            publication_revision: 5,
            latest_operation_kind: "publish",
            latest_operation_state: "succeeded",
            latest_operation_at: "2026-08-20T10:00:00Z",
            latest_operation_error: "",
            active_publication_id: "pub-active",
            previous_publication_id: "pub-previous",
            active_publication: {
              publication_id: "pub-active",
              artifact_digest: "digest-active",
            },
            previous_publication: {
              publication_id: "pub-previous",
              artifact_digest: "digest-previous",
            },
          },
        };
        const compactRunning = {
          kb_id: "same-kb",
          profile: " GENERAL ",
          status: "stale",
          usable: true,
          fallback_mode: "agentic",
          serving_stale: true,
          stale_confirmed: true,
          stale_severity: "soft_stale",
          stale_reasons: ["metadata_updated"],
          source_state: { state: "stale", serving_allowed: true },
          event_generation: 6,
          pending_evaluation_generation: 6,
          evaluated_generation: 5,
          automation_state: "running",
          automatic_build_enabled: true,
          automatic_publish_enabled: true,
          pending_generation: 6,
          running_generation: 5,
          last_attempt_publication_id: "attempt-new",
          last_success_at: "2026-08-20T10:02:00Z",
          last_error: "ready_data source evaluation is pending",
          latest_operation_kind: "build",
          latest_operation_state: "running",
          latest_operation_at: "2026-08-20T10:02:00Z",
          latest_operation_error: "",
          current_ready_index_version_id: "index-current-new",
          smoke_status: "failed",
          smoke_checked_at: "2026-08-20T10:03:00Z",
          publication_revision: 5,
        };
        const running = selectReadyDataManifestUpdate(
          full,
          compactRunning,
          "same-kb",
          true,
        );
        for (const key of [
          "status",
          "usable",
          "fallback_mode",
          "serving_stale",
          "stale_confirmed",
          "stale_severity",
          "stale_reasons",
          "source_state",
          "event_generation",
          "pending_evaluation_generation",
          "evaluated_generation",
          "automation_state",
          "automatic_build_enabled",
          "automatic_publish_enabled",
          "pending_generation",
          "running_generation",
          "last_attempt_publication_id",
          "last_success_at",
          "last_error",
          "latest_operation_kind",
          "latest_operation_state",
          "latest_operation_at",
          "latest_operation_error",
          "current_ready_index_version_id",
          "smoke_status",
          "smoke_checked_at",
        ]) assert.deepEqual(running[key], compactRunning[key], key);
        assert.equal(running.publication_state.active_publication, full.publication_state.active_publication);
        assert.equal(running.publication_state.previous_publication, full.publication_state.previous_publication);
        assert.equal(running.publication_state.latest_operation_kind, "build");
        assert.equal(running.publication_state.latest_operation_state, "running");
        assert.equal(running.publication_state.latest_operation_at, "2026-08-20T10:02:00Z");
        assert.equal(running.authoritative_source_version_id, "source-authoritative");
        assert.equal(running.observed_index_version_id, "index-observed");
        assert.equal(running.artifact_digest, "digest-active");
        assert.equal(shouldPollReadyDataManifest(running, 0, 12), true);

        const compactSucceeded = {
          ...compactRunning,
          status: "ready",
          serving_stale: false,
          stale_confirmed: false,
          stale_severity: "none",
          stale_reasons: [],
          source_state: { state: "fresh", serving_allowed: true },
          automation_state: "succeeded",
          pending_generation: null,
          running_generation: null,
          last_error: null,
          latest_operation_kind: "build",
          latest_operation_state: "succeeded",
          latest_operation_at: "2026-08-20T10:04:00Z",
          latest_operation_error: "",
        };
        const succeeded = selectReadyDataManifestUpdate(
          running,
          compactSucceeded,
          "same-kb",
          true,
        );
        assert.equal(succeeded.automation_state, "succeeded");
        assert.equal(succeeded.serving_stale, false);
        assert.equal(succeeded.publication_state.active_publication, full.publication_state.active_publication);
        assert.equal(succeeded.publication_state.latest_operation_kind, "build");
        assert.equal(succeeded.publication_state.latest_operation_state, "succeeded");
        assert.deepEqual(resolveReadyDataOperationState(succeeded), {
          kind: "build",
          status: "succeeded",
          error: "",
          at: "2026-08-20T10:04:00Z",
          source: "publication_state",
        });
        assert.equal(shouldPollReadyDataManifest(succeeded, 0, 12), false);

        const generalRevisionEight = {
          ...full,
          publication_revision: 8,
          publication_state: {
            ...full.publication_state,
            publication_revision: 8,
          },
        };
        const formulaRevisionZero = {
          ...full,
          profile: "formula",
          publication_revision: 0,
          publication_state: {
            ...full.publication_state,
            publication_revision: 0,
            active_publication_id: "formula-active",
          },
        };
        const formula = selectReadyDataManifestUpdate(
          generalRevisionEight,
          formulaRevisionZero,
          "same-kb",
          true,
        );
        assert.equal(formula, formulaRevisionZero);
        assert.equal(
          selectReadyDataManifestUpdate(
            formula,
            generalRevisionEight,
            "same-kb",
            false,
          ),
          formula,
        );
        assert.equal(
          selectReadyDataMutationProfile("same-kb", formula, "same-kb", "general"),
          "formula",
        );
        assert.equal(
          selectReadyDataMutationProfile(
            "same-kb",
            { ...formula, profile: " Formula " },
            "same-kb",
            "general",
          ),
          "formula",
        );

        const deferred = () => {
          let resolve;
          const promise = new Promise((yes) => { resolve = yes; });
          return { promise, resolve };
        };
        let nextManifestVersion = 0;
        let appliedManifestVersion = 0;
        let view = [{
          id: "A",
          name: "A-current",
          manifest_profile: "general",
          agentic_ready_manifest: {
            ...full,
            kb_id: "A",
          },
        }];
        const oldList = deferred();
        const requestVersion = ++nextManifestVersion;
        const oldListRun = oldList.promise.then((response) => {
          const authoritative = isReadyDataKnowledgeListManifestAuthoritative(
            requestVersion,
            appliedManifestVersion,
          );
          if (authoritative) appliedManifestVersion = requestVersion;
          view = mergeReadyDataKnowledgeList(
            view,
            response,
            authoritative,
          );
        });
        const buildVersion = ++nextManifestVersion;
        const buildAuthoritative = isReadyDataKnowledgeListManifestAuthoritative(
          buildVersion,
          appliedManifestVersion,
        );
        if (buildAuthoritative) appliedManifestVersion = buildVersion;
        view = mergeReadyDataKnowledgeManifest(view, "A", {
          ...full,
          kb_id: "A",
          automation_state: "running",
          automatic_build_enabled: true,
        }, buildAuthoritative);
        oldList.resolve([
          { id: "B", name: "B-from-old-get" },
          {
            id: "A",
            name: "A-from-old-get",
            manifest_profile: "general",
            agentic_ready_manifest: {
              ...full,
              kb_id: "A",
              automation_state: "idle",
            },
          },
        ]);
        await oldListRun;
        assert.deepEqual(view.map((item) => item.id), ["B", "A"]);
        assert.equal(view[1].name, "A-from-old-get");
        assert.equal(view[1].agentic_ready_manifest.automation_state, "running");

        const newRequestVersion = ++nextManifestVersion;
        const newRequestAuthoritative = isReadyDataKnowledgeListManifestAuthoritative(
          newRequestVersion,
          appliedManifestVersion,
        );
        if (newRequestAuthoritative) appliedManifestVersion = newRequestVersion;
        view = mergeReadyDataKnowledgeList(view, [
          {
            id: "A",
            name: "A-from-new-get",
            manifest_profile: "general",
            agentic_ready_manifest: {
              ...full,
              kb_id: "A",
              automation_state: "succeeded",
            },
          },
        ], newRequestAuthoritative);
        assert.equal(view[0].agentic_ready_manifest.automation_state, "succeeded");
        assert.equal(shouldPollReadyDataManifest(view[0].agentic_ready_manifest, 0, 12), false);

        // A later request that fails never becomes applied authority, so it
        // cannot suppress an earlier successful mutation response.
        const nextBuildVersion = ++nextManifestVersion;
        const failedGetVersion = ++nextManifestVersion;
        assert.ok(failedGetVersion > nextBuildVersion);
        assert.equal(
          isReadyDataKnowledgeListManifestAuthoritative(
            nextBuildVersion,
            appliedManifestVersion,
          ),
          true,
        );

        const profileList = mergeReadyDataKnowledgeList([
          {
            id: "A",
            name: "A-general",
            manifest_profile: "general",
            agentic_ready_manifest: { ...generalRevisionEight, kb_id: "A" },
          },
        ], [
          { id: "B", name: "B-formula" },
          {
            id: "A",
            name: "A-formula",
            manifest_profile: "formula",
            agentic_ready_manifest: { ...formulaRevisionZero, kb_id: "A" },
          },
        ], true);
        assert.deepEqual(profileList.map((item) => item.id), ["B", "A"]);
        assert.equal(profileList[1].manifest_profile, "formula");
        assert.equal(profileList[1].agentic_ready_manifest.profile, "formula");
        """
    )


def test_detail_manifest_episodes_order_cross_source_successes() -> None:
    _run_typescript(
        """
        const assert = (await import("node:assert/strict")).default;
        const imported = await import("./client/src/lib/ready-data-ui-state.ts");
        const {
          readyDataManifestAfterLoad,
          resolveReadyDataManifestEpisode,
          selectReadyDataManifestEpisodeUpdate,
          selectReadyDataManifestUpdate,
          shouldPollReadyDataManifest,
        } = imported.default || imported;

        const full = (profile, state, suffix) => ({
          kb_id: "detail-kb",
          profile,
          status: state === "running" ? "stale" : "ready",
          usable: true,
          serving_stale: state === "running",
          stale_severity: state === "running" ? "soft_stale" : "none",
          stale_reasons: state === "running" ? ["metadata_updated"] : [],
          automation_state: state,
          publication_revision: 5,
          observed_index_version_id: `observed-${suffix}`,
          current_ready_index_version_id: `current-${suffix}`,
          artifact_digest: `digest-${suffix}`,
          publication_state: {
            publication_revision: 5,
            active_publication_id: `active-${suffix}`,
            previous_publication_id: `previous-${suffix}`,
            active_publication: { publication_id: `active-${suffix}` },
            previous_publication: { publication_id: `previous-${suffix}` },
          },
        });
        const compact = (profile, state) => ({
          kb_id: "detail-kb",
          profile,
          status: state === "running" ? "stale" : "ready",
          usable: true,
          serving_stale: state === "running",
          stale_severity: state === "running" ? "soft_stale" : "none",
          automation_state: state,
          publication_revision: 5,
        });

        let applied = null;
        let current = null;
        const apply = (incoming, version) => {
          const decision = resolveReadyDataManifestEpisode(
            "detail-kb",
            incoming,
            version,
            applied,
          );
          assert.equal(decision.applicable, true);
          applied = decision.applied;
          current = selectReadyDataManifestUpdate(
            current,
            incoming,
            "detail-kb",
            decision.authoritative,
          );
          return decision;
        };

        // Meta starts first, but a newer dedicated response applies first.
        const oldMetaVersion = 1;
        const dedicatedVersion = 2;
        apply(full("formula", "running", "formula"), dedicatedVersion);
        const oldMeta = apply(compact("general", "succeeded"), oldMetaVersion);
        assert.equal(oldMeta.authoritative, false);
        assert.equal(current.profile, "formula");
        assert.equal(current.automation_state, "running");
        assert.equal(current.publication_state.active_publication_id, "active-formula");
        assert.equal(shouldPollReadyDataManifest(current, 0, 12), true);

        // A newer compact success may refresh dynamic state without losing the
        // complete projection, and an older full response cannot undo it.
        const oldRunningVersion = 3;
        const newSucceededVersion = 4;
        apply(compact("formula", "succeeded"), newSucceededVersion);
        assert.equal(current.automation_state, "succeeded");
        assert.equal(current.publication_state.active_publication_id, "active-formula");
        assert.equal(shouldPollReadyDataManifest(current, 0, 12), false);
        const oldRunning = apply(full("formula", "running", "old-running"), oldRunningVersion);
        assert.equal(oldRunning.authoritative, false);
        assert.equal(current.automation_state, "succeeded");
        assert.equal(current.publication_state.active_publication_id, "active-formula");

        // A later-started failure never advances applied authority, so an
        // earlier request that eventually succeeds may still apply.
        const earlierSuccessVersion = 5;
        const laterFailedVersion = 6;
        assert.ok(laterFailedVersion > earlierSuccessVersion);
        const beforeFailure = applied;
        // A failed request never calls the resolver.
        assert.equal(applied, beforeFailure);
        const earlierSuccess = apply(compact("formula", "running"), earlierSuccessVersion);
        assert.equal(earlierSuccess.authoritative, true);
        assert.equal(current.automation_state, "running");

        // If a later loader error temporarily clears the dedicated state, an
        // older non-authoritative response must not recreate its old profile.
        const staleAfterClear = resolveReadyDataManifestEpisode(
          "detail-kb",
          compact("general", "succeeded"),
          2,
          applied,
        );
        assert.equal(staleAfterClear.authoritative, false);
        assert.equal(
          selectReadyDataManifestEpisodeUpdate(
            null,
            compact("general", "succeeded"),
            "detail-kb",
            staleAfterClear,
          ),
          null,
        );

        // A failed forced refresh preserves the last successfully applied view.
        assert.equal(
          readyDataManifestAfterLoad(current, null, false, true),
          current,
        );
        """
    )


def test_knowledge_manifest_episodes_are_scoped_per_kb_and_profile() -> None:
    _run_typescript(
        """
        const assert = (await import("node:assert/strict")).default;
        const imported = await import("./client/src/lib/ready-data-ui-state.ts");
        const {
          mergeReadyDataKnowledgeList,
          mergeReadyDataKnowledgeManifest,
          resolveReadyDataManifestEpisode,
          shouldPollReadyDataManifest,
        } = imported.default || imported;

        const manifest = (kbId, profile, state, suffix) => ({
          kb_id: kbId,
          profile,
          status: state === "running" ? "stale" : "ready",
          usable: true,
          automation_state: state,
          publication_revision: 5,
          artifact_digest: `digest-${suffix}`,
          publication_state: {
            publication_revision: 5,
            active_publication_id: `active-${suffix}`,
          },
        });
        let nextVersion = 0;
        const appliedByKb = new Map();
        const decide = (kbId, incoming, version) => {
          const decision = resolveReadyDataManifestEpisode(
            kbId,
            incoming,
            version,
            appliedByKb.get(kbId) || null,
          );
          if (decision.applicable && decision.authoritative) {
            appliedByKb.set(kbId, decision.applied);
          }
          return decision.authoritative;
        };

        let view = [
          {
            id: "A",
            name: "A-current",
            manifest_profile: "general",
            agentic_ready_manifest: manifest("A", "general", "idle", "a-old"),
          },
          {
            id: "B",
            name: "B-current",
            manifest_profile: "general",
            agentic_ready_manifest: manifest("B", "general", "idle", "b-old"),
          },
        ];
        const oldListVersion = ++nextVersion;

        // Only B receives a newer build. A must not inherit B's applied episode.
        const bBuildVersion = ++nextVersion;
        const bFormula = manifest("B", "formula", "running", "b-build");
        view = mergeReadyDataKnowledgeManifest(
          view,
          "B",
          bFormula,
          decide("B", bFormula, bBuildVersion),
        );
        assert.equal(view[1].manifest_profile, "formula");

        const oldList = [
          { id: "C", name: "C-added" },
          {
            id: "B",
            name: "B-from-old-list",
            manifest_profile: "general",
            agentic_ready_manifest: manifest("B", "general", "idle", "b-list-old"),
          },
          {
            id: "A",
            name: "A-from-old-list",
            manifest_profile: "general",
            agentic_ready_manifest: manifest("A", "general", "running", "a-list"),
          },
        ];
        const authorityByKb = new Map();
        for (const item of oldList) {
          if (!item.agentic_ready_manifest) continue;
          authorityByKb.set(
            item.id,
            decide(item.id, item.agentic_ready_manifest, oldListVersion),
          );
        }
        view = mergeReadyDataKnowledgeList(
          view,
          oldList,
          (kbId) => authorityByKb.get(kbId) || false,
        );
        assert.deepEqual(view.map((item) => item.id), ["C", "B", "A"]);
        assert.equal(view[1].name, "B-from-old-list");
        assert.equal(view[1].manifest_profile, "formula");
        assert.equal(view[1].agentic_ready_manifest.profile, "formula");
        assert.equal(view[1].agentic_ready_manifest.artifact_digest, "digest-b-build");
        assert.equal(view[2].agentic_ready_manifest.automation_state, "running");
        assert.equal(shouldPollReadyDataManifest(view[2].agentic_ready_manifest, 0, 12), true);

        // A subsequent successful list request becomes authoritative per item.
        const newListVersion = ++nextVersion;
        const newList = [
          {
            id: "A",
            name: "A-from-new-list",
            manifest_profile: "formula",
            agentic_ready_manifest: manifest("A", "formula", "succeeded", "a-formula"),
          },
          {
            id: "B",
            name: "B-from-new-list",
            manifest_profile: "formula",
            agentic_ready_manifest: manifest("B", "formula", "succeeded", "b-new"),
          },
        ];
        const nextAuthority = new Map();
        for (const item of newList) {
          nextAuthority.set(
            item.id,
            decide(item.id, item.agentic_ready_manifest, newListVersion),
          );
        }
        view = mergeReadyDataKnowledgeList(
          view,
          newList,
          (kbId) => nextAuthority.get(kbId) || false,
        );
        assert.deepEqual(view.map((item) => item.id), ["A", "B"]);
        assert.equal(view[0].manifest_profile, "formula");
        assert.equal(view[0].agentic_ready_manifest.profile, "formula");
        assert.equal(view[0].agentic_ready_manifest.automation_state, "succeeded");
        assert.equal(appliedByKb.get("A").profile, "formula");
        assert.equal(appliedByKb.get("B").profile, "formula");

        // A failed request does not call decide and cannot advance either KB.
        const failedVersion = ++nextVersion;
        assert.ok(failedVersion > appliedByKb.get("A").version);
        assert.equal(appliedByKb.get("A").version, newListVersion);
        assert.equal(appliedByKb.get("B").version, newListVersion);
        """
    )


def test_latest_build_episode_refreshes_equal_revision_full_snapshot() -> None:
    _run_typescript(
        """
        const assert = (await import("node:assert/strict")).default;
        const imported = await import("./client/src/lib/ready-data-ui-state.ts");
        const {
          readyDataManifestAfterLoad,
          resolveReadyDataManifestEpisode,
          selectReadyDataManifestUpdate,
        } = imported.default || imported;

        const snapshot = (suffix, stale) => ({
          kb_id: "build-kb",
          profile: "general",
          status: stale ? "stale" : "ready",
          usable: true,
          serving_stale: stale,
          stale_severity: stale ? "soft_stale" : "none",
          stale_reasons: stale ? ["ready_index_changed"] : [],
          automation_state: stale ? "running" : "succeeded",
          publication_revision: 5,
          observed_index_version_id: "observed-stable",
          current_ready_index_version_id: `current-${suffix}`,
          artifact_digest: "digest-stable",
          publication_state: {
            publication_revision: 5,
            active_publication_id: "active-stable",
            previous_publication_id: "previous-stable",
            active_publication: {
              publication_id: "active-stable",
              observed_index_version_id: "observed-stable",
            },
            previous_publication: { publication_id: "previous-stable" },
          },
        });
        let current = snapshot("old", true);
        let applied = { profile: "general", version: 1 };
        const buildVersion = 2;
        const buildSnapshot = snapshot("new", false);
        const buildDecision = resolveReadyDataManifestEpisode(
          "build-kb",
          buildSnapshot,
          buildVersion,
          applied,
        );
        assert.equal(buildDecision.authoritative, true);
        applied = buildDecision.applied;
        current = selectReadyDataManifestUpdate(
          current,
          buildSnapshot,
          "build-kb",
          buildDecision.authoritative,
        );
        assert.equal(current.current_ready_index_version_id, "current-new");
        assert.equal(current.serving_stale, false);
        assert.equal(current.publication_state.active_publication_id, "active-stable");
        assert.equal(current.publication_state.previous_publication_id, "previous-stable");
        assert.equal(current.observed_index_version_id, "observed-stable");
        assert.equal(
          readyDataManifestAfterLoad(current, null, false, true),
          current,
        );

        // A newer successful GET wins; the older delayed build cannot roll it back.
        const delayedBuildVersion = 3;
        const newerGetVersion = 4;
        const newest = snapshot("newest", false);
        const getDecision = resolveReadyDataManifestEpisode(
          "build-kb",
          newest,
          newerGetVersion,
          applied,
        );
        applied = getDecision.applied;
        current = selectReadyDataManifestUpdate(
          current,
          newest,
          "build-kb",
          getDecision.authoritative,
        );
        const delayedBuild = snapshot("delayed-build", true);
        const delayedDecision = resolveReadyDataManifestEpisode(
          "build-kb",
          delayedBuild,
          delayedBuildVersion,
          applied,
        );
        assert.equal(delayedDecision.authoritative, false);
        current = selectReadyDataManifestUpdate(
          current,
          delayedBuild,
          "build-kb",
          delayedDecision.authoritative,
        );
        assert.equal(current.current_ready_index_version_id, "current-newest");
        assert.equal(current.serving_stale, false);
        """
    )


def test_safe_build_snapshot_uses_server_monotonic_freshness_after_older_get() -> None:
    _run_typescript(
        """
        const assert = (await import("node:assert/strict")).default;
        const imported = await import("./client/src/lib/ready-data-ui-state.ts");
        const {
          mergeReadyDataKnowledgeManifest,
          readyDataManifestAfterLoad,
          resolveReadyDataManifestEpisode,
          resolveReadyDataSafeMutationManifestEpisode,
          selectReadyDataManifestEpisodeUpdate,
        } = imported.default || imported;

        const snapshot = ({
          revision = 5,
          eventGeneration,
          evaluatedGeneration,
          index,
          stale,
          digest = "digest-stable",
        }) => ({
          kb_id: "freshness-kb",
          profile: "general",
          status: stale ? "stale" : "ready",
          usable: true,
          serving_stale: stale,
          stale_severity: stale ? "soft_stale" : "none",
          stale_reasons: stale ? ["ready_index_changed"] : [],
          automation_state: stale ? "idle" : "succeeded",
          event_generation: eventGeneration,
          evaluated_generation: evaluatedGeneration,
          publication_revision: revision,
          observed_index_version_id: "observed-stable",
          current_ready_index_version_id: index,
          artifact_digest: digest,
          publication_state: {
            publication_revision: revision,
            active_publication_id: "active-stable",
            previous_publication_id: "previous-stable",
            active_publication: {
              publication_id: "active-stable",
              observed_index_version_id: "observed-stable",
              artifact_digest: digest,
            },
            previous_publication: { publication_id: "previous-stable" },
          },
        });

        // The build starts first. A GET that read before the build committed then
        // applies first, but the safe build response proves a later evaluation.
        const buildVersion = 1;
        const getVersion = 2;
        let applied = null;
        let current = null;
        const staleGet = snapshot({
          eventGeneration: 7,
          evaluatedGeneration: 6,
          index: "idx-old",
          stale: true,
        });
        const getDecision = resolveReadyDataManifestEpisode(
          "freshness-kb",
          staleGet,
          getVersion,
          applied,
        );
        applied = getDecision.applied;
        current = selectReadyDataManifestEpisodeUpdate(
          current,
          staleGet,
          "freshness-kb",
          getDecision,
        );
        const freshBuild = snapshot({
          eventGeneration: 7,
          evaluatedGeneration: 7,
          index: "idx-new",
          stale: false,
        });
        const buildDecision = resolveReadyDataSafeMutationManifestEpisode(
          "freshness-kb",
          current,
          freshBuild,
          buildVersion,
          applied,
        );
        assert.equal(buildDecision.authoritative, true);
        assert.equal(buildDecision.applied.version, getVersion);
        current = selectReadyDataManifestEpisodeUpdate(
          current,
          freshBuild,
          "freshness-kb",
          buildDecision,
        );
        assert.equal(current.current_ready_index_version_id, "idx-new");
        assert.equal(current.serving_stale, false);
        assert.equal(current.automation_state, "succeeded");
        assert.equal(current.publication_state.active_publication_id, "active-stable");
        assert.equal(current.publication_state.previous_publication_id, "previous-stable");
        assert.equal(current.observed_index_version_id, "observed-stable");
        assert.equal(
          readyDataManifestAfterLoad(current, null, false, true),
          current,
        );

        // Knowledge uses the same evidence-aware decision, not a separate rule.
        let list = [{
          id: "freshness-kb",
          manifest_profile: "general",
          agentic_ready_manifest: staleGet,
        }];
        const listDecision = resolveReadyDataSafeMutationManifestEpisode(
          "freshness-kb",
          list[0].agentic_ready_manifest,
          freshBuild,
          buildVersion,
          { profile: "general", version: getVersion },
        );
        list = mergeReadyDataKnowledgeManifest(
          list,
          "freshness-kb",
          freshBuild,
          listDecision.authoritative,
        );
        assert.equal(list[0].agentic_ready_manifest.current_ready_index_version_id, "idx-new");
        assert.equal(list[0].agentic_ready_manifest.serving_stale, false);

        // Strictly older server evidence cannot win just because a response is late.
        for (const newerCurrent of [
          snapshot({
            revision: 6,
            eventGeneration: 7,
            evaluatedGeneration: 7,
            index: "idx-published-newer",
            stale: false,
          }),
          snapshot({
            eventGeneration: 8,
            evaluatedGeneration: 8,
            index: "idx-evaluated-newer",
            stale: false,
          }),
        ]) {
          const olderBuild = snapshot({
            eventGeneration: 7,
            evaluatedGeneration: 7,
            index: "idx-delayed-old-build",
            stale: true,
          });
          const rejected = resolveReadyDataSafeMutationManifestEpisode(
            "freshness-kb",
            newerCurrent,
            olderBuild,
            9,
            { profile: "general", version: 2 },
          );
          assert.equal(rejected.authoritative, false);
          const selected = selectReadyDataManifestEpisodeUpdate(
            newerCurrent,
            olderBuild,
            "freshness-kb",
            rejected,
          );
          assert.equal(selected.current_ready_index_version_id, newerCurrent.current_ready_index_version_id);
          assert.equal(selected.serving_stale, false);
        }
        """
    )
