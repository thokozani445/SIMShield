import { useState, useEffect } from "react";
import { getHealth } from "../lib/apiClient";

export function useHealth() {
  const [health, setHealth] = useState(null);
  const [online, setOnline] = useState(null);

  useEffect(() => {
    getHealth()
      .then(d => { setHealth(d); setOnline(true);  })
      .catch(() =>               setOnline(false));
  }, []);

  return { health, online };
}