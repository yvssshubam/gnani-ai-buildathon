import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "./api.js";

/** Polls the control room board. Returns { board, error, refresh }. */
export function useBoard(intervalMs = 1500) {
  const [board, setBoard] = useState(null);
  const [error, setError] = useState(null);
  const timer = useRef(null);

  const refresh = useCallback(async () => {
    try {
      setBoard(await api.board());
      setError(null);
    } catch (e) {
      setError(e.message || "Can't reach the server");
    }
  }, []);

  useEffect(() => {
    let stopped = false;
    const tick = async () => {
      await refresh();
      if (!stopped) timer.current = setTimeout(tick, intervalMs);
    };
    tick();
    return () => { stopped = true; clearTimeout(timer.current); };
  }, [refresh, intervalMs]);

  return { board, error, refresh };
}
