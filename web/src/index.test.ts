import { describe, expect, it } from "vitest";

import { APP_NAME } from "./index";

describe("frontend bootstrap", () => {
  it("el paquete importa", () => {
    expect(APP_NAME).toBe("Carmen");
  });
});
