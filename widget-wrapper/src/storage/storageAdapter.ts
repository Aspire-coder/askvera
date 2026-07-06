export type StorageAdapter = {
  getItem(key: string): string | undefined;
  setItem(key: string, value: string): void;
  removeItem(key: string): void;
};

export const createMemoryStorageAdapter = (): StorageAdapter => {
  const store = new Map<string, string>();

  return {
    getItem: (key) => store.get(key),
    setItem: (key, value) => {
      store.set(key, value);
    },
    removeItem: (key) => {
      store.delete(key);
    }
  };
};
