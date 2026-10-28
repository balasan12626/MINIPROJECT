import { afterEach, describe, expect, it, vi } from "vitest";
import { registerPhoneOffline } from "./offlinePages.js";

afterEach(() => vi.unstubAllGlobals());

describe("phone pages offline shell (F15)", () => {
  it("does nothing outside a production build", () => {
    const register = vi.fn();
    vi.stubGlobal("navigator", { serviceWorker: { register } });
    expect(registerPhoneOffline({ enabled: false })).toBe(false);
    expect(register).not.toHaveBeenCalled();
  });

  it("registers /sw.js and hands it the build files already loaded", async () => {
    const postMessage = vi.fn();
    const reg = { active: { postMessage } };
    const register = vi.fn().mockResolvedValue(reg);
    vi.stubGlobal("navigator", { serviceWorker: { register, ready: Promise.resolve(reg) } });
    vi.spyOn(performance, "getEntriesByType").mockReturnValue([
      { name: "http://localhost/assets/CitizenSos-abc.js" },
      { name: "https://tile.openstreetmap.org/1/1/1.png" },
    ]);
    expect(registerPhoneOffline({ enabled: true })).toBe(true);
    await vi.waitFor(() => expect(postMessage).toHaveBeenCalled());
    expect(register).toHaveBeenCalledWith("/sw.js");
    const msg = postMessage.mock.calls[0][0];
    expect(msg.type).toBe("cache-assets");
    expect(msg.urls).toEqual(["http://localhost/assets/CitizenSos-abc.js"]);
  });
});
