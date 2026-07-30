import { createMemoryStorageAdapter, type StorageAdapter } from "./storageAdapter";

export function createSessionStorageAdapter(): StorageAdapter {
  if (typeof sessionStorage === "undefined") {
    return createMemoryStorageAdapter();
  }

  return {
    getItem: (key) => sessionStorage.getItem(key) || undefined,
    setItem: (key, value) => {
      sessionStorage.setItem(key, value);
    },
    removeItem: (key) => {
      sessionStorage.removeItem(key);
    }
  };
}
