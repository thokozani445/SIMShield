import { useState, useEffect, useRef } from "react";
import { getEvents } from "../lib/apiClient";

export function useEvents({ interval = 3000, limit = 20 } = {}) {
  const [events,  setEvents]  = useState([]);
  const [loading, setLoading] = useState(true);
  const timer = useRef(null);

  async function poll() {
    try {
      const d = await getEvents({ limit });
      setEvents(d.events);
    } catch (_) {
      // Silent — polling should never crash the UI
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    poll();
    timer.current = setInterval(poll, interval);
    return () => clearInterval(timer.current);
  }, [interval, limit]);

  return { events, loading };
}