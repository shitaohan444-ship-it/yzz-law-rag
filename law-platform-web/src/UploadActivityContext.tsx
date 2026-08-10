import { createContext, type ReactNode, useCallback, useContext, useMemo, useState } from 'react';

export interface UploadActivity {
  busy: boolean;
  activeCount: number;
  progressText: string;
}

interface UploadActivityContextValue {
  activity: UploadActivity;
  reportActivity: (activity: Partial<UploadActivity>) => void;
}

const UploadActivityContext = createContext<UploadActivityContextValue | null>(null);

export function UploadActivityProvider({ children }: { children: ReactNode }) {
  const [activity, setActivity] = useState<UploadActivity>({
    busy: false,
    activeCount: 0,
    progressText: '',
  });

  const reportActivity = useCallback((partial: Partial<UploadActivity>) => {
    setActivity((prev) => ({ ...prev, ...partial }));
  }, []);

  const value = useMemo(() => ({ activity, reportActivity }), [activity, reportActivity]);

  return (
    <UploadActivityContext.Provider value={value}>
      {children}
    </UploadActivityContext.Provider>
  );
}

export function useUploadActivity(): UploadActivityContextValue {
  const ctx = useContext(UploadActivityContext);
  if (!ctx) {
    throw new Error('useUploadActivity must be used within UploadActivityProvider');
  }
  return ctx;
}
