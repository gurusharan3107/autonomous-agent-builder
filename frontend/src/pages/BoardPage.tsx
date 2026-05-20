import { useEffect, useState } from "react";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  ErrorState,
  LoadingState,
  PageFrame,
  PageHeader,
  StatusDot,
} from "@/design-system";
import { BoardLane } from "@/features/board/BoardLane";
import { BoardSprintStrip } from "@/features/board/BoardSprintStrip";
import { SprintDetailSidebar } from "@/features/board/SprintDetailSidebar";
import { TaskDetailSidebar } from "@/features/board/TaskDetailSidebar";
import {
  IMPLEMENTATION_STATUSES,
  LANE_ORDER,
  sprintShippedHistoryTasks,
  sprintStageFromPhase,
  sprintStageFromVisibleTasks,
  taskSprintId,
  type LaneKey,
  type SprintStage,
} from "@/features/board/board-model";
import { dispatchTask, fetchBoard, openBoardStream, recoverTask } from "@/lib/api";
import { useBoardAnimations } from "@/hooks/use-board-animations";
import { useRuntimePreferences } from "@/hooks/use-runtime-preferences";
import type { BoardData, TaskBoardItem } from "@/lib/types";

function LiveBoardPulse({ live }: { live: boolean }) {
  return (
    <span className="inline-flex items-center gap-2 font-mono text-[10.5px] uppercase tracking-[0.18em] text-muted-foreground">
      <StatusDot tone={live ? "active" : "muted"} pulse={live} className="h-2 w-2" />
      Stream · {live ? "live" : "loading"}
    </span>
  );
}

export default function BoardPage() {
  const { preferences } = useRuntimePreferences();
  const animRef = useBoardAnimations();
  const density = preferences.boardDensity;
  const [board, setBoard] = useState<BoardData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [dispatchingTaskId, setDispatchingTaskId] = useState<string | null>(null);
  const [recoveringTaskId, setRecoveringTaskId] = useState<string | null>(null);
  const [selectedTaskId, setSelectedTaskId] = useState<string | null>(null);
  const [sprintDetailStage, setSprintDetailStage] = useState<SprintStage | null>(null);
  const [selectedSprintId, setSelectedSprintId] = useState<string>("");
  const [streamKey, setStreamKey] = useState(0);

  const loadFallback = async () => {
    try {
      const data = await fetchBoard();
      setBoard(data);
      setError(null);
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "Failed to load board");
    }
  };

  useEffect(() => {
    let active = true;
    let receivedSnapshot = false;
    void loadFallback();
    const stream = openBoardStream((data) => {
      if (!active) return;
      receivedSnapshot = true;
      setBoard(data);
      setError(null);
    });

    stream.onerror = () => {
      if (!active) return;
      if (!receivedSnapshot) {
        void loadFallback();
      }
    };

    return () => {
      active = false;
      stream.close();
    };
  }, [streamKey]);

  useEffect(() => {
    if (!board) return;
    const sprintIds = new Set((board.sprints ?? []).map((sprint) => sprint.sprint_id));
    const currentId = board.current_sprint?.sprint_id ?? "";
    if (!selectedSprintId || (selectedSprintId !== "all" && !sprintIds.has(selectedSprintId))) {
      setSelectedSprintId(currentId || "all");
    }
  }, [board, selectedSprintId]);

  const sprints = board?.sprints ?? [];
  const selectedSprint = sprints.find((sprint) => sprint.sprint_id === selectedSprintId) ?? board?.current_sprint ?? null;
  const selectedPlan =
    selectedSprint && selectedSprint.sprint_id === board?.current_sprint?.sprint_id
      ? board?.sprint_plan
      : null;
  const selectedSprintTaskIds = new Set(selectedSprint?.generated_task_ids ?? []);
  const filterTasks = (tasks: TaskBoardItem[]) => {
    if (!selectedSprint || selectedSprintId === "all") return tasks;
    return tasks.filter((task) => selectedSprintTaskIds.has(task.id) || taskSprintId(task) === selectedSprint.sprint_id);
  };
  const filteredBoard: Record<LaneKey, TaskBoardItem[]> = board
    ? {
        pending: filterTasks(board.pending),
        active: filterTasks(board.active),
        review: filterTasks(board.review),
        done: [
          ...filterTasks(board.done),
          ...sprintShippedHistoryTasks(
            selectedSprint,
            new Set(
              [...board.pending, ...board.active, ...board.review, ...board.done, ...board.blocked]
                .map((task) => task.id),
            ),
          ),
        ],
        blocked: filterTasks(board.blocked),
      }
    : { pending: [], active: [], review: [], done: [], blocked: [] };
  const allTasks = LANE_ORDER.flatMap((lane) => filteredBoard[lane.key]);
  const selectedTask = allTasks.find((task) => task.id === selectedTaskId) ?? null;
  const hasRunningTask = filteredBoard.active.some((task) => task.latest_run_status === "running");
  const hasStartedWork =
    filteredBoard.active.length > 0
    || filteredBoard.review.length > 0
    || filteredBoard.blocked.length > 0
    || filteredBoard.done.length > 0;
  const hasUnresolvedStartedWork =
    filteredBoard.active.length > 0
    || filteredBoard.review.length > 0
    || filteredBoard.blocked.length > 0;
  const dispatchableTask = filteredBoard.active[0] ?? filteredBoard.pending[0] ?? null;
  const activeSprintStage: SprintStage | null =
    sprintStageFromVisibleTasks(filteredBoard)
    ?? sprintStageFromPhase(selectedSprint?.active_phase)
    ?? (filteredBoard.active.some((task) => IMPLEMENTATION_STATUSES.has(task.status)) ? "implementation" : null);

  const handleDispatch = async () => {
    if (!dispatchableTask) return;
    setDispatchingTaskId(dispatchableTask.id);
    try {
      await dispatchTask(dispatchableTask.id);
    } catch (dispatchError) {
      setError(dispatchError instanceof Error ? dispatchError.message : "Failed to dispatch task");
    } finally {
      setDispatchingTaskId(null);
    }
  };

  const handleRecover = async (task: TaskBoardItem) => {
    setRecoveringTaskId(task.id);
    setError(null);
    try {
      await recoverTask(task.id);
      setBoard(await fetchBoard());
    } catch (recoverError) {
      setError(recoverError instanceof Error ? recoverError.message : "Failed to recover task");
    } finally {
      setRecoveringTaskId(null);
    }
  };

  if (error && !board) {
    return <ErrorState message={error} onRetry={() => setStreamKey((value) => value + 1)} />;
  }

  if (!board) {
    return <LoadingState label="Loading pipeline..." />;
  }

  return (
    <PageFrame variant="overview" data-screen-label="Board">
      <PageHeader
        eyebrow="Work board"
        title="Every improvement, one horizon."
        description="Track what is ready, in motion, waiting for review, blocked, and shipped without leaving the Builder workspace."
        aside={
          <div className="flex flex-wrap items-center justify-end gap-2">
            <LiveBoardPulse live={Boolean(board)} />
            <Select value={selectedSprintId || board.current_sprint?.sprint_id || "all"} onValueChange={setSelectedSprintId}>
              <SelectTrigger className="h-9 min-w-[150px] justify-between rounded-full" aria-label="Select sprint">
                <SelectValue placeholder="Select sprint" />
              </SelectTrigger>
              <SelectContent align="end">
                {sprints.map((sprint) => (
                  <SelectItem key={sprint.sprint_id} value={sprint.sprint_id}>
                    {sprint.label}
                  </SelectItem>
                ))}
                <SelectItem value="all">All sprints</SelectItem>
              </SelectContent>
            </Select>
          </div>
        }
      />

      <div ref={animRef} className="space-y-4">
        <div data-board-section>
          <BoardSprintStrip
            plan={selectedPlan}
            currentSprint={selectedSprint}
            activeStage={activeSprintStage}
            dispatchableTask={dispatchableTask}
            dispatchingTaskId={dispatchingTaskId}
            hasRunningTask={hasRunningTask}
            hasStartedWork={hasStartedWork}
            hasUnresolvedStartedWork={hasUnresolvedStartedWork}
            onDispatch={handleDispatch}
            onOpenStage={setSprintDetailStage}
          />
        </div>

        {error ? (
          <div data-board-section>
            <ErrorState message={error} onRetry={() => setStreamKey((value) => value + 1)} />
          </div>
        ) : null}

        <div data-board-section className="grid gap-4 xl:grid-cols-5">
          {LANE_ORDER.map((lane) => (
            <div key={lane.key} data-slot="card">
              <BoardLane
                title={lane.title}
                tasks={filteredBoard[lane.key]}
                density={density}
                tone={lane.tone}
                onSelect={(task) => setSelectedTaskId(task.id)}
                onRecover={lane.key === "blocked" ? handleRecover : undefined}
                recoveringTaskId={recoveringTaskId}
              />
            </div>
          ))}
        </div>
        <TaskDetailSidebar task={selectedTask} onClose={() => setSelectedTaskId(null)} />
        <SprintDetailSidebar
          stage={sprintDetailStage}
          plan={selectedPlan}
          currentSprint={selectedSprint}
          activeTasks={filteredBoard.active.filter((task) => IMPLEMENTATION_STATUSES.has(task.status))}
          sprintTasks={allTasks.filter((task) => taskSprintId(task) === (selectedSprint?.sprint_id ?? ""))}
          onClose={() => setSprintDetailStage(null)}
        />
      </div>
    </PageFrame>
  );
}
