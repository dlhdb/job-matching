import { afterEach, describe, expect, it, vi } from "vitest";

import { readStore, writeStore } from "./storage";

function fakeStorage(): Storage {
  const data = new Map<string, string>();
  return {
    getItem: (key) => data.get(key) ?? null,
    setItem: (key, value) => void data.set(key, value),
    removeItem: (key) => void data.delete(key),
    clear: () => data.clear(),
    key: (index) => [...data.keys()][index] ?? null,
    get length() {
      return data.size;
    },
  };
}

// 模擬不允許保存的瀏覽器：讀寫都丟出例外
const blocked = {
  getItem: () => {
    throw new DOMException("blocked", "SecurityError");
  },
  setItem: () => {
    throw new DOMException("blocked", "SecurityError");
  },
};

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("readStore", () => {
  it("讀出寫入的值", () => {
    vi.stubGlobal("localStorage", fakeStorage());
    writeStore("k", { a: 1 });
    expect(readStore("k")).toEqual({ a: 1 });
  });

  it("沒有記錄時是 null", () => {
    vi.stubGlobal("localStorage", fakeStorage());
    expect(readStore("k")).toBeNull();
  });

  it("內容不是 JSON 時是 null", () => {
    const storage = fakeStorage();
    storage.setItem("k", "{壞掉");
    vi.stubGlobal("localStorage", storage);
    expect(readStore("k")).toBeNull();
  });

  it("瀏覽器不允許保存時是 null，不丟出例外", () => {
    vi.stubGlobal("localStorage", blocked);
    expect(readStore("k")).toBeNull();
  });
});

describe("writeStore", () => {
  it("瀏覽器不允許保存時不丟出例外", () => {
    vi.stubGlobal("localStorage", blocked);
    expect(() => writeStore("k", 1)).not.toThrow();
  });
});
