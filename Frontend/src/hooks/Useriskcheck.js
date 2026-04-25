import { useState, useCallback } from "react";
import { checkRisk } from "../lib/apiClient";

export function useRiskCheck() {
  const [result,  setResult]  = useState(null);
  const [loading, setLoading] = useState(false);
  const [error,   setError]   = useState(null);

  const check = useCallback(async (payload) => {
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      setResult(await checkRisk(payload));
    } catch (e) {
      setError({ message: e.message, code: e.code });
    } finally {
      setLoading(false);
    }
  }, []);

  const reset = useCallback(() => {
    setResult(null);
    setError(null);
    setLoading(false);
  }, []);

  return { result, loading, error, check, reset };
}