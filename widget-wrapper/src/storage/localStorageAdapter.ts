import { createMemoryStorageAdapter, type StorageAdapter } from "./storageAdapter";

export function createLocalStorageAdapter(): StorageAdapter {
  if (typeof localStorage === "undefined") {
    return createMemoryStorageAdapter();
  }

  return {
    getItem: (key) => localStorage.getItem(key) || undefined,
    setItem: (key, value) => {
      localStorage.setItem(key, value);
    },
    removeItem: (key) => {
      localStorage.removeItem(key);
    }
  };
}
