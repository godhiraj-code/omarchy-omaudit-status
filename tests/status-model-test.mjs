import assert from "node:assert/strict"
import { createRequire } from "node:module"

const require = createRequire(import.meta.url)
const Model = require("../StatusModel.js")
// Freeze wall time for these historical contract fixtures. Reliability tests
// separately exercise expiry and clock skew with explicit timestamps.
Date.now = () => Date.parse("2026-08-24T12:00:00+00:00")

assert.equal(Model.shouldPublishScan(4, 4), true)
assert.equal(Model.shouldPublishScan(4, 5), false)
assert.equal(Model.shouldPublishScan(-1, -1), false)

function plugin(overrides = {}) {
  const value = {
    id: "example.plugin",
    name: "Example",
    version: "1.0.0",
    grade: "A",
    score: 95,
    status: "unchanged",
    firstParty: false,
    added: [],
    composition: [],
    evidence: {},
    ...overrides
  }
  if (value.status === "changed" && !("added" in overrides)) value.added = ["capability.test"]
  return value
}

function documentFor(plugins = [], overrides = {}) {
  const unchanged = plugins.filter(item => item.status === "unchanged").length
  const changed = plugins.filter(item => item.status === "changed").length
  const notTracked = plugins.filter(item => item.status === "not-tracked").length
  const compositionRisks = plugins.filter(item => item.composition.length > 0).length
  const statusText = changed > 0
    ? `${changed} ${changed === 1 ? "plugin" : "plugins"} changed`
    : (notTracked > 0
      ? `${notTracked} ${notTracked === 1 ? "plugin needs" : "plugins need"} baseline`
      : (plugins.length > 0 ? "All tracked plugins unchanged" : "No plugins found"))
  return {
    schemaVersion: 1,
    ok: true,
    installed: true,
    scannedAt: "2026-08-24T12:00:00+00:00",
    statusText,
    worstGrade: plugins.length ? plugins[0].grade : "",
    totals: { plugins: plugins.length, unchanged, changed, notTracked, compositionRisks },
    plugins,
    error: "",
    ...overrides
  }
}

const clean = Model.validateDocument(documentFor([plugin()]))
assert.equal(clean.valid, true)
assert.equal(Model.state(clean.document), "clean")
assert.equal(Model.tone(clean.document), "positive")
assert.equal(Model.colorKey(clean.document), "green")
assert.match(Model.summary(clean.document), /unchanged/i)

const hostileLabel = '</Text><img src="file:///etc/passwd"> 中文 مرحبا'
const hostileText = Model.validateDocument(documentFor([
  plugin({ id: "hostile.plugin", name: hostileLabel })
]))
assert.equal(hostileText.valid, true)
assert.equal(hostileText.document.plugins[0].name, hostileLabel)

const untracked = Model.validateDocument(documentFor([
  plugin({ status: "not-tracked", grade: "", score: 0 })
]))
assert.equal(untracked.valid, true)
assert.equal(Model.state(untracked.document), "untracked")
assert.equal(Model.tone(untracked.document), "caution")
assert.equal(Model.colorKey(untracked.document), "amber")
assert.match(Model.summary(untracked.document), /baseline review/i)

const changed = Model.validateDocument(documentFor([
  plugin({ status: "changed", grade: "D", score: 42, added: ["net.outbound"] })
]))
assert.equal(changed.valid, true)
assert.equal(Model.state(changed.document), "changed")
assert.equal(Model.tone(changed.document), "critical")
assert.equal(Model.colorKey(changed.document), "red")
assert.match(Model.summary(changed.document), /capability drift/i)

const composition = Model.validateDocument(documentFor([
  plugin({ grade: "C", composition: ["credentials plus outbound network"] })
]))
assert.equal(composition.valid, true)
assert.equal(Model.state(composition.document), "composition-risk")
assert.equal(Model.tone(composition.document), "critical")
assert.equal(Model.colorKey(composition.document), "red")
assert.match(Model.summary(composition.document), /composition risk/i)

const adapterError = Model.validateDocument(documentFor([], {
  ok: false,
  installed: true,
  statusText: "Scan failed",
  error: "Omaudit returned malformed JSON"
}))
assert.equal(adapterError.valid, true)
assert.equal(Model.state(adapterError.document), "error")
assert.equal(Model.tone(adapterError.document), "dim")
assert.equal(Model.colorKey(adapterError.document), "dim")
assert.match(Model.summary(adapterError.document), /review unavailable/i)

for (const malformed of [
  "not-json",
  null,
  [],
  { schemaVersion: 2 },
  documentFor([], { ok: "yes" }),
  documentFor([], { totals: { plugins: -1, unchanged: 0, changed: 0, notTracked: 0, compositionRisks: 0 } }),
  documentFor([plugin({ firstParty: "false" })]),
  documentFor([plugin()], { totals: { plugins: 2, unchanged: 1, changed: 0, notTracked: 0, compositionRisks: 0 } })
]) {
  const result = Model.validateDocument(malformed)
  assert.equal(result.valid, false)
  assert.equal(Model.state(result.document), "error")
  assert.notEqual(Model.colorKey(result.document), "green")
}

const contradictory = Model.validateDocument(documentFor([], {
  scannedAt: "not-a-time",
  statusText: "Scan failed",
  error: "adapter failed"
}))
assert.equal(contradictory.valid, false)
assert.equal(Model.state(contradictory.document), "error")
assert.equal(Model.colorKey(contradictory.document), "dim")

for (const falseGreenProbe of [
  documentFor([], { scannedAt: "0" }),
  documentFor([], { scannedAt: "2026-02-31T12:00:00+00:00" }),
  documentFor([], { statusText: "Scan failed" }),
  documentFor([plugin({ name: " " })])
]) {
  const result = Model.validateDocument(falseGreenProbe)
  assert.equal(result.valid, false)
  assert.equal(Model.state(result.document), "error")
  assert.equal(Model.colorKey(result.document), "dim")
}

assert.equal(Model.validateDocument(documentFor([], {
  scannedAt: "2028-02-29T23:59:59+00:00"
})).valid, true)

for (const crossFieldProbe of [
  plugin({ id: "unchanged-added", added: ["net.outbound"] }),
  plugin({ id: "unchanged-evidence", evidence: { "net.outbound": { file: "Panel.qml", line: 9 } } }),
  plugin({ id: "untracked-added", status: "not-tracked", grade: "", added: ["net.outbound"] }),
  plugin({ id: "changed-empty", status: "changed", grade: "F", added: [] }),
  plugin({
    id: "changed-unrelated-evidence",
    status: "changed",
    grade: "F",
    added: ["process.exec"],
    evidence: { "net.outbound": { file: "Panel.qml", line: 9 } }
  })
]) {
  const result = Model.validateDocument(documentFor([crossFieldProbe]))
  assert.equal(result.valid, false)
  assert.equal(Model.state(result.document), "error")
  assert.equal(Model.colorKey(result.document), "dim")
}

for (const duplicateId of ["same", "__proto__", "constructor", "toString"]) {
  const duplicateIds = Model.validateDocument(documentFor([
    plugin({ id: duplicateId }), plugin({ id: duplicateId })
  ]))
  assert.equal(duplicateIds.valid, false)
  assert.equal(Model.state(duplicateIds.document), "error")
}

const boundedPlugins = Array.from({ length: 100 }, (_, index) => plugin({
  id: `p-${String(index).padStart(3, "0")}`, status: "changed"
}))
const boundedRisk = Model.validateDocument(documentFor(boundedPlugins, {
  worstGrade: "F",
  totals: { plugins: 101, unchanged: 1, changed: 100, notTracked: 0, compositionRisks: 1 }
}))
assert.equal(boundedRisk.valid, true)
assert.equal(Model.state(boundedRisk.document), "composition-risk")
assert.equal(Model.colorKey(boundedRisk.document), "red")

const unsorted = Model.validateDocument(documentFor([
  plugin({ id: "clean", status: "unchanged", grade: "A" }),
  plugin({ id: "changed", status: "changed", grade: "F" })
], { worstGrade: "F" }))
assert.equal(unsorted.valid, false)
assert.equal(Model.state(unsorted.document), "error")

const wording = [
  Model.summary(clean.document),
  Model.summary(untracked.document),
  Model.summary(changed.document),
  Model.summary(composition.document),
  Model.summary(adapterError.document)
].join(" ").toLowerCase()
assert.match(wording, /review/)
assert.doesNotMatch(wording, /malware|safe|infected|threat detected/)

assert.deepEqual(Model.visiblePlugins(documentFor([
  plugin({ id: "a" }), plugin({ id: "b" }), plugin({ id: "c" })
]), 2).map(item => item.id), ["a", "b"])
assert.equal(Model.scanTime(clean.document), "2026-08-24 12:00 UTC")
assert.equal(Model.ipcStatus(clean.document, false), JSON.stringify({
  schemaVersion: 1,
  state: "clean",
  scanning: false,
  scannedAt: "2026-08-24T12:00:00+00:00",
  totals: { plugins: 1, unchanged: 1, changed: 0, notTracked: 0, compositionRisks: 0 }
}))

console.log("status model tests passed")
