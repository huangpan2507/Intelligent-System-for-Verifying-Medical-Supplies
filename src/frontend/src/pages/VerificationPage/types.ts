export type ActionFeedback = {
  act: (action: () => Promise<void>) => Promise<void>;
  setNotice: (message: string) => void;
  setError: (message: string) => void;
};
