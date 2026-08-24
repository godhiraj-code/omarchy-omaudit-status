var VALID_STATUS = { "unchanged": true, "changed": true, "not-tracked": true }
var VALID_GRADE = { "": true, "A": true, "B": true, "C": true, "D": true, "F": true }
var GRADE_RANK = { "F": 0, "D": 1, "C": 2, "B": 3, "A": 4, "": 5 }
var STATUS_RANK = { "changed": 0, "not-tracked": 1, "unchanged": 2 }

function zeroTotals() {
  return { plugins: 0, unchanged: 0, changed: 0, notTracked: 0, compositionRisks: 0 }
}

function errorDocument(message, installed) {
  return {
    schemaVersion: 1,
    ok: false,
    installed: installed !== false,
    scannedAt: "",
    statusText: "Scan unavailable",
    worstGrade: "",
    totals: zeroTotals(),
    plugins: [],
    error: String(message || "Invalid status document").substring(0, 160)
  }
}

function plainObject(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value)
}

function integerInRange(value, minimum, maximum) {
  return typeof value === "number" && isFinite(value)
    && Math.floor(value) === value && value >= minimum && value <= maximum
}

function boundedString(value, maximum, allowEmpty) {
  if (typeof value !== "string" || value.length > maximum) return false
  if (value.length === 0) return allowEmpty === true
  return value.trim().length > 0 && value === value.trim()
}

function validUtcTimestamp(value) {
  if (typeof value !== "string") return false
  var match = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})\+00:00$/.exec(value)
  if (!match) return false
  var date = new Date(0)
  date.setUTCFullYear(Number(match[1]), Number(match[2]) - 1, Number(match[3]))
  date.setUTCHours(Number(match[4]), Number(match[5]), Number(match[6]), 0)
  return date.getUTCFullYear() === Number(match[1])
    && date.getUTCMonth() === Number(match[2]) - 1
    && date.getUTCDate() === Number(match[3])
    && date.getUTCHours() === Number(match[4])
    && date.getUTCMinutes() === Number(match[5])
    && date.getUTCSeconds() === Number(match[6])
}

function expectedStatusText(totals) {
  if (totals.changed > 0)
    return totals.changed + (totals.changed === 1 ? " plugin changed" : " plugins changed")
  if (totals.notTracked > 0)
    return totals.notTracked + (totals.notTracked === 1 ? " plugin needs baseline" : " plugins need baseline")
  return totals.plugins > 0 ? "All tracked plugins unchanged" : "No plugins found"
}

function stringArray(value, maximumItems, maximumLength) {
  if (!Array.isArray(value) || value.length > maximumItems) return false
  for (var i = 0; i < value.length; i++) {
    if (!boundedString(value[i], maximumLength, false)) return false
  }
  return true
}

function validEvidence(value) {
  if (!plainObject(value)) return false
  var keys = Object.keys(value)
  if (keys.length > 12) return false
  for (var i = 0; i < keys.length; i++) {
    var key = keys[i]
    var location = value[key]
    if (!boundedString(key, 200, false) || !plainObject(location)
        || !boundedString(location.file, 255, false)
        || !integerInRange(location.line, 1, 1000000000)) return false
  }
  return true
}

function validPlugin(plugin) {
  if (!(plainObject(plugin)
    && boundedString(plugin.id, 200, false)
    && boundedString(plugin.name, 200, false)
    && boundedString(plugin.version, 100, false)
    && VALID_GRADE[plugin.grade] === true
    && integerInRange(plugin.score, 0, 100)
    && VALID_STATUS[plugin.status] === true
    && typeof plugin.firstParty === "boolean"
    && stringArray(plugin.added, 12, 300)
    && stringArray(plugin.composition, 6, 300)
    && validEvidence(plugin.evidence))) return false

  var evidenceKeys = Object.keys(plugin.evidence)
  if ((plugin.status === "unchanged" || plugin.status === "not-tracked")
      && (plugin.added.length > 0 || evidenceKeys.length > 0)) return false
  if (plugin.status === "changed" && plugin.added.length === 0) return false
  for (var i = 0; i < evidenceKeys.length; i++) {
    if (plugin.added.indexOf(evidenceKeys[i]) < 0) return false
  }
  return true
}

function comparePlugins(left, right) {
  var statusDifference = STATUS_RANK[left.status] - STATUS_RANK[right.status]
  if (statusDifference !== 0) return statusDifference
  var gradeDifference = GRADE_RANK[left.grade] - GRADE_RANK[right.grade]
  if (gradeDifference !== 0) return gradeDifference
  if (left.id < right.id) return -1
  if (left.id > right.id) return 1
  return 0
}

function validateDocument(input) {
  var value = input
  if (typeof value === "string") {
    try {
      value = JSON.parse(value)
    } catch (error) {
      return { valid: false, document: errorDocument("Malformed adapter output") }
    }
  }

  if (!plainObject(value) || value.schemaVersion !== 1
      || typeof value.ok !== "boolean" || typeof value.installed !== "boolean"
      || !boundedString(value.scannedAt, 80, true)
      || !boundedString(value.statusText, 300, true)
      || !boundedString(value.worstGrade, 8, true) || VALID_GRADE[value.worstGrade] !== true
      || !boundedString(value.error, 300, true)
      || !plainObject(value.totals) || !Array.isArray(value.plugins)
      || value.plugins.length > 100) {
    return { valid: false, document: errorDocument("Invalid adapter status document") }
  }

  var totals = value.totals
  var totalKeys = ["plugins", "unchanged", "changed", "notTracked", "compositionRisks"]
  for (var t = 0; t < totalKeys.length; t++) {
    if (!integerInRange(totals[totalKeys[t]], 0, 1000000))
      return { valid: false, document: errorDocument("Invalid adapter totals") }
  }

  var counts = zeroTotals()
  var seenPluginIds = []
  counts.plugins = value.plugins.length
  for (var i = 0; i < value.plugins.length; i++) {
    var plugin = value.plugins[i]
    if (!validPlugin(plugin))
      return { valid: false, document: errorDocument("Invalid adapter plugin entry") }
    if (seenPluginIds.indexOf(plugin.id) >= 0)
      return { valid: false, document: errorDocument("Duplicate adapter plugin ID") }
    seenPluginIds.push(plugin.id)
    if (i > 0 && comparePlugins(value.plugins[i - 1], plugin) > 0)
      return { valid: false, document: errorDocument("Unsorted adapter plugin entries") }
    if (plugin.status === "unchanged") counts.unchanged++
    else if (plugin.status === "changed") counts.changed++
    else counts.notTracked++
    if (plugin.composition.length > 0) counts.compositionRisks++
  }

  if (totals.unchanged + totals.changed + totals.notTracked !== totals.plugins
      || totals.compositionRisks > totals.plugins
      || value.plugins.length !== Math.min(totals.plugins, 100)
      || counts.unchanged > totals.unchanged
      || counts.changed > totals.changed
      || counts.notTracked > totals.notTracked
      || counts.compositionRisks > totals.compositionRisks)
    return { valid: false, document: errorDocument("Inconsistent adapter totals") }

  if (value.ok === true) {
    if (value.installed !== true || value.error !== ""
        || !validUtcTimestamp(value.scannedAt)
        || value.statusText !== expectedStatusText(totals))
      return { valid: false, document: errorDocument("Contradictory adapter success document") }

    var visibleWorst = ""
    for (var g = 0; g < value.plugins.length; g++) {
      var grade = value.plugins[g].grade
      if (GRADE_RANK[grade] < GRADE_RANK[visibleWorst]) visibleWorst = grade
    }
    if (totals.plugins <= 100) {
      if (value.worstGrade !== visibleWorst)
        return { valid: false, document: errorDocument("Inconsistent adapter worst grade") }
    } else if (GRADE_RANK[value.worstGrade] > GRADE_RANK[visibleWorst]) {
      return { valid: false, document: errorDocument("Inconsistent adapter worst grade") }
    }
  } else {
    if (value.error === "" || totals.plugins !== 0 || value.plugins.length !== 0
        || value.worstGrade !== "" || !validUtcTimestamp(value.scannedAt)
        || value.statusText !== (value.installed ? "Scan failed" : "Omaudit not installed"))
      return { valid: false, document: errorDocument("Contradictory adapter error document") }
  }

  return { valid: true, document: value }
}

function state(document) {
  var doc = plainObject(document) ? document : errorDocument()
  if (doc.ok !== true || doc.installed !== true || doc.error !== ""
      || !validUtcTimestamp(doc.scannedAt)) return "error"
  var totals = plainObject(doc.totals) ? doc.totals : zeroTotals()
  if (totals.compositionRisks > 0) return "composition-risk"
  if (totals.changed > 0) return "changed"
  if (totals.notTracked > 0) return "untracked"
  return "clean"
}

function tone(document) {
  var current = state(document)
  if (current === "error") return "dim"
  if (current === "untracked") return "caution"
  if (current === "changed" || current === "composition-risk") return "critical"
  return "positive"
}

function colorKey(document) {
  var currentTone = tone(document)
  if (currentTone === "positive") return "green"
  if (currentTone === "caution") return "amber"
  if (currentTone === "critical") return "red"
  return "dim"
}

function plural(count, singular, pluralForm) {
  return count + " " + (count === 1 ? singular : pluralForm)
}

function summary(document) {
  var doc = plainObject(document) ? document : errorDocument()
  var current = state(doc)
  var totals = plainObject(doc.totals) ? doc.totals : zeroTotals()
  if (current === "error") {
    return doc.installed === false
      ? "Omaudit is not installed; capability review unavailable"
      : "Capability review unavailable"
  }
  if (current === "composition-risk")
    return plural(totals.compositionRisks, "composition risk", "composition risks") + " need review"
  if (current === "changed")
    return plural(totals.changed, "plugin has", "plugins have") + " capability drift to review"
  if (current === "untracked")
    return plural(totals.notTracked, "plugin needs", "plugins need") + " baseline review"
  if (totals.plugins === 0) return "No third-party plugins found"
  return "Tracked plugin capabilities are unchanged"
}

function visiblePlugins(document, limit) {
  var list = plainObject(document) && Array.isArray(document.plugins) ? document.plugins : []
  var maximum = integerInRange(limit, 0, 100) ? limit : 8
  return list.slice(0, maximum)
}

function scanTime(document) {
  var raw = plainObject(document) ? String(document.scannedAt || "") : ""
  if (raw === "") return "Not scanned yet"
  var date = new Date(raw)
  if (!isFinite(date.getTime())) return "Unknown scan time"
  function pad(value) { return value < 10 ? "0" + value : String(value) }
  return date.getUTCFullYear() + "-" + pad(date.getUTCMonth() + 1) + "-" + pad(date.getUTCDate())
    + " " + pad(date.getUTCHours()) + ":" + pad(date.getUTCMinutes()) + " UTC"
}

function ipcStatus(document, scanning) {
  var doc = plainObject(document) ? document : errorDocument()
  return JSON.stringify({
    schemaVersion: 1,
    state: state(doc),
    scanning: scanning === true,
    scannedAt: String(doc.scannedAt || ""),
    totals: plainObject(doc.totals) ? doc.totals : zeroTotals()
  })
}

if (typeof module !== "undefined") {
  module.exports = {
    zeroTotals: zeroTotals,
    errorDocument: errorDocument,
    validateDocument: validateDocument,
    state: state,
    tone: tone,
    colorKey: colorKey,
    summary: summary,
    visiblePlugins: visiblePlugins,
    scanTime: scanTime,
    ipcStatus: ipcStatus
  }
}
