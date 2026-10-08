import "./setup.ts";
import assert from "node:assert/strict";
import { test } from "node:test";
import { safeReturn } from "@aihot/backend/admin/auth";

test("admin login may return to the protected WeRSS entry", () => {
  for (const target of ["/admin", "/admin/sources", "/werss/", "/werss/weread", "/werss/?page=2"]) {
    assert.equal(safeReturn(target), target);
  }
});

test("admin login rejects redirect and path-normalization escapes", () => {
  for (const target of ["//example.com/werss/", "/werssevil", "/werss/../all", "/werss/%2e%2e/all", "/werss/%5cevil", "/werss/\nevil", "/werss/%00evil", "/werss/%zz", "/all"]) {
    assert.equal(safeReturn(target), "/admin");
  }
});
