import { useCallback, useEffect, useRef } from "react";

export function useLatestRequestGuard(identity: string): (requestIdentity: string) => () => boolean {
  const identityRef = useRef(identity);
  const generationRef = useRef(0);
  identityRef.current = identity;

  useEffect(() => () => {
    generationRef.current += 1;
  }, []);

  return useCallback((requestIdentity: string) => {
    if (identityRef.current !== requestIdentity) return () => false;
    const generation = ++generationRef.current;
    return () => identityRef.current === requestIdentity && generationRef.current === generation;
  }, []);
}
