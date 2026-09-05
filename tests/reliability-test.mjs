import assert from 'node:assert/strict'
import { test } from 'node:test'
import { createRequire } from 'node:module'
import { readFileSync, mkdtempSync, writeFileSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join, resolve, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'
import { spawnSync } from 'node:child_process'
import vm from 'node:vm'

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const Model = createRequire(import.meta.url)('../StatusModel.js')
const now = Date.parse('2026-09-05T12:00:00+00:00')
const clean = () => ({schemaVersion: 1, ok: true, installed: true,
  scannedAt: '2026-09-05T12:00:00+00:00', statusText: 'No plugins found',
  worstGrade: '', totals: Model.zeroTotals(), plugins: [], error: ''})

// Execute the actual QML JavaScript bodies, with explicit Process/Timer doubles.
// This checks lifecycle policy, not Qt signal delivery or native focus/layout.
export function body(source, marker) {
  const start = source.indexOf(marker)
  assert.notEqual(start, -1, `missing ${marker}`)
  const opening = source.indexOf('{', start)
  let depth = 1, end = opening + 1
  for (; depth && end < source.length; end++) {
    if (source[end] === '{') depth++
    if (source[end] === '}') depth--
  }
  return source.slice(opening + 1, end - 1)
}

function service() {
  const source = readFileSync(join(root, 'Service.qml'), 'utf8')
  const queued = [], launches = [], signals = []
  const timer = () => ({running: false, restart() {this.running = true}, stop() {this.running = false}})
  const c = {StatusModel: Model, Date, Math, Number, String, isFinite,
    status: clean(), scanning: false, includeBuiltins: false, adapterPath: '/isolated/status.py',
    refreshIntervalSec: 900, maxAdapterOutputChars: 128, nowMs: now,
    _stdout: '', _outputOverflow: false, _startupScanStarted: false, _refreshPending: false,
    _configurationGeneration: 0, _activeGeneration: -1, _failure: '',
    scanProcess: {running: false, processId: 42, command: [], signal(n) {signals.push(n)}},
    watchdog: timer(), startDeadline: timer(), killDeadline: timer(),
    Qt: {callLater(fn) {queued.push(fn)}},
    Quickshell: {execDetached(argv) {launches.push(Array.from(argv))}}}
  c.root = c
  vm.createContext(c)
  for (const match of source.matchAll(/^  function (\w+)\(([^)]*)\) \{/gm)) {
    c[match[1]] = vm.runInContext(`(function(${match[2]}) {${body(source, match[0])}})`, c)
  }
  const handler = (name, args = '') => vm.runInContext(`(function(${args}) {${body(source, name)}})`, c)
  return {c, queued, launches, signals, exit: handler('onExited:', 'exitCode, exitStatus'),
    runningChanged: () => {
      // The handler executes in Process scope in QML.
      c.running = c.scanProcess.running
      handler('onRunningChanged:')()
    }, started: () => handler('onStarted:')()}
}

test('complete success JSON requires normal zero adapter exit', () => {
  for (const [code, status] of [[9, 0], [0, 1], [0, 0]]) {
    const s = service(); s.c.maxAdapterOutputChars = 10000; s.c.refresh()
    s.c.ingestStdout(JSON.stringify(clean())); s.c.scanProcess.running = false
    s.exit(code, status)
    assert.equal(s.c.status.ok, code === 0 && status === 0)
    assert.equal(s.c.scanning, false)
  }
})

test('failed start without exited recovers; normal exit does not become start failure', () => {
  const s = service(); s.c.refresh(); s.c.scanProcess.running = false; s.runningChanged()
  assert.equal(s.c.scanning, false); assert.match(s.c.status.error, /start/i)
  assert.equal(s.c.refresh(), true)
  s.c.maxAdapterOutputChars = 10000; s.c.ingestStdout(JSON.stringify(clean()))
  s.c.scanProcess.running = false; s.exit(0, 0); s.runningChanged()
  assert.equal(s.c.status.ok, true)
})

test('startup deadline, watchdog and overflow terminate gracefully then bound hard fallback', () => {
  for (const trigger of ['startTimedOut', 'scanTimedOut', 'overflow']) {
    const s = service(); s.c.refresh()
    assert.equal(s.c.watchdog.running, true); assert.equal(s.c.startDeadline.running, true)
    if (trigger === 'overflow') s.c.ingestStdout('x'.repeat(129))
    else s.c[trigger]()
    assert.equal(s.c.status.ok, false); assert.deepEqual(s.signals, [15])
    assert.equal(s.c.refresh(), false)
    s.c.hardStop(); assert.deepEqual(s.signals, [15, 9])
    s.c.scanProcess.running = false; s.exit(0, 0)
    assert.equal(s.c.status.ok, false); assert.equal(s.c.scanning, false)
    assert.equal(s.c.killDeadline.running, false); assert.equal(s.c.refresh(), true)
  }
})

test('started cancels startup deadline; no PID never signals process group zero', () => {
  const s = service(); s.c.refresh(); s.started()
  assert.equal(s.c.startDeadline.running, false)
  s.c.scanProcess.processId = 0; s.c.startTimedOut(); s.c.hardStop()
  assert.deepEqual(s.signals, [])
})

test('rapid scope changes discard old output and launch one current replacement', () => {
  const s = service(); s.c.maxAdapterOutputChars = 10000; s.c.refresh()
  for (const scope of [true, false, true]) s.c.configure({includeBuiltins: scope})
  s.c.ingestStdout(JSON.stringify(clean())); s.c.scanProcess.running = false; s.exit(0, 0)
  assert.equal(s.c.status.ok, false); assert.equal(s.queued.length, 1)
  s.queued.shift()(); assert.equal(s.c.scanning, true)
  assert.deepEqual(Array.from(s.c.scanProcess.command), ['python3', '/isolated/status.py', '--include-builtins'])
  s.c.ingestStdout(JSON.stringify(clean())); s.c.scanProcess.running = false; s.exit(0, 0)
  assert.equal(s.c.status.ok, true); assert.equal(s.queued.length, 0)
})

test('scope replacement survives a failed start or obsolete watchdog failure', () => {
  for (const failure of ['start', 'watchdog']) {
    const s = service(); s.c.refresh(); s.c.configure({includeBuiltins: true})
    if (failure === 'watchdog') s.c.scanTimedOut()
    s.c.scanProcess.running = false
    if (failure === 'start') s.runningChanged()
    else s.exit(9, 1)
    assert.match(s.c.status.error, /scope changed/i)
    assert.equal(s.queued.length, 1); s.queued.shift()()
    assert.equal(s.c._activeGeneration, s.c._configurationGeneration)
    assert.equal(s.c._failure, ''); assert.equal(s.c.scanning, true)
  }
})

test('watchdog and startup/kill timer bindings execute the intended lifecycle paths', () => {
  const source = readFileSync(join(root, 'Service.qml'), 'utf8')
  for (const [id, milliseconds] of [['startDeadline', 10000], ['watchdog', 150000], ['killDeadline', 5000]]) {
    const start = source.indexOf(`id: ${id}`)
    const timer = source.slice(start, source.indexOf('\n  }', start))
    assert.match(timer, new RegExp(`interval: ${milliseconds}`))
    const callback = /onTriggered: (.*)/.exec(timer)[1]
    const s = service(); s.c.refresh()
    if (id === 'killDeadline') s.c.scanTimedOut()
    vm.runInContext(callback, s.c)
    assert.deepEqual(s.signals, id === 'killDeadline' ? [15, 9] : [15])
    assert.equal(s.c.status.ok, false)
  }
})

test('review uses exactly two fixed scope commands and skips missing dependency', () => {
  const s = service(); s.c.review(); s.c.includeBuiltins = true; s.c.review()
  assert.deepEqual(s.launches, [
    ['omarchy-launch-floating-terminal-with-presentation', 'omaudit check'],
    ['omarchy-launch-floating-terminal-with-presentation', 'omaudit check --all']])
  s.c.status.installed = false; assert.equal(s.c.review(), false); assert.equal(s.launches.length, 2)
})

test('freshness, refresh age, bounded future tolerance, and scope neutral empty summary', () => {
  const doc = clean()
  assert.equal(Model.state(doc, now, 210), 'clean')
  assert.equal(Model.state(doc, now + 211000, 210), 'stale')
  assert.equal(Model.colorKey(doc, now + 211000, 210), 'dim')
  assert.match(Model.freshnessText(doc, true, now + 5000, 210), /Refreshing.*5s ago/)
  assert.match(Model.summary(doc, now, 210), /No plugins found/)
  assert.equal(Model.state(doc, now - 30001, 210), 'stale')
  assert.equal(Model.state(doc, now - 30000, 210), 'clean')
  assert.doesNotMatch(Model.freshnessText(doc, false, now - 1000, 210), /-1/)
  doc.scannedAt = '2000-01-01T00:00:00+00:00'
  assert.equal(Model.state(doc, now, 210), 'stale')
})

test('display escapes bidi and controls with bounded intact Unicode and useful errors', () => {
  assert.equal(Model.displayText('Weather\u202Eabc\u2069\u0000', 200), 'Weather\\u202Eabc\\u2069\\u0000')
  assert.equal(Model.displayText('हिंदी 🛡️', 200), 'हिंदी 🛡️')
  assert.ok(Array.from(Model.displayText('\u202E'.repeat(500), 300)).length <= 300)
  assert.equal(Model.displayText('🛡'.repeat(201), 200), '🛡'.repeat(200))
  for (const reason of ['scan timed out', 'Malformed adapter output', 'output exceeded size limit'])
    assert.equal(Model.displayText(Model.errorDocument(reason).error, 300), reason)
})

test('panel keyboard selection skips disabled actions and reveals controls after manual scrolling', () => {
  const source = readFileSync(join(root, 'Panel.qml'), 'utf8')
  const c = {Math, selectedAction: 1, canRefresh: false, canReview: true,
    scroller: {contentY: 0, contentHeight: 1100, height: 300},
    actionRow: {y: 1040, height: 60}, Qt: {callLater(fn) {fn()}}, refreshes: 0, reviews: 0}
  c.root = c; vm.createContext(c)
  for (const name of ['scrollContent', 'revealAction', 'selectAction', 'activateAction']) {
    const match = new RegExp(`function ${name}\\(([^)]*)\\)`).exec(source)
    assert.ok(match, `missing ${name}`)
    c[name] = vm.runInContext(`(function(${match[1]}) {${body(source, match[0])}})`, c)
  }
  c.refresh = () => c.refreshes++; c.review = () => c.reviews++
  c.selectAction(); assert.equal(c.selectedAction, 1); assert.equal(c.scroller.contentY, 800)
  c.scrollContent(-5000); assert.equal(c.scroller.contentY, 0)
  c.selectAction(); assert.equal(c.scroller.contentY, 800)
  c.canRefresh = true; c.selectAction(); assert.equal(c.selectedAction, 0)
  c.activateAction(); assert.equal(c.refreshes, 1)
  c.canRefresh = false; c.activateAction(); assert.equal(c.refreshes, 1)
  c.canReview = false; c.selectAction(); assert.equal(c.selectedAction, -1)
  c.activateAction(); assert.equal(c.reviews, 0)
  c.scrollContent(9999); assert.equal(c.scroller.contentY, 800)
  c.scroller.contentHeight = 100; c.scrollContent(9999); assert.equal(c.scroller.contentY, 0)
  c.popupOpen = true; c.canRefresh = true; c.canReview = false
  vm.runInContext(body(source, 'onPopupOpenChanged:'), c)
  assert.equal(c.selectedAction, 0, 'opening with missing Omaudit selects enabled Refresh')
  Object.assign(c.Qt, {Key_PageDown: 1, Key_PageUp: 2, Key_Home: 3, Key_End: 4})
  const keyHandler = vm.runInContext(`(function(event) {${body(source, 'Keys.onPressed:')}})`, c)
  c.scroller.contentHeight = 1100
  for (const [key, position] of [[1, 240], [2, 0], [4, 800], [3, 0]]) {
    const event = {key, accepted: false}; keyHandler(event)
    assert.equal(event.accepted, true); assert.equal(c.scroller.contentY, position)
  }
  const escape = {key: 99, accepted: false}; keyHandler(escape)
  assert.equal(escape.accepted, false, 'unhandled keys remain available to host dispatcher')
})

test('panel wires sanitized errors, separate stable identity/grade, freshness and keyboard scroll', () => {
  const source = readFileSync(join(root, 'Panel.qml'), 'utf8')
  assert.match(source, /StatusModel\.displayText\(root\.statusDocument\.error, 300\)/)
  assert.match(source, /StatusModel\.displayText\(modelData\.id, 200\)/)
  assert.match(source, /text: "Grade " \+ \(modelData\.grade/)
  assert.match(source, /StatusModel\.freshnessText/)
  assert.match(source, /Keys\.forwardTo: \[scrollKeys\]/)
  assert.match(source, /Item \{\s+id: scrollKeys\s+Keys\.onPressed:/)
  assert.match(source, /Qt\.Key_PageDown/)
  assert.match(source, /Qt\.Key_Home/)
  assert.match(source, /root\.selectAction\(\)/)
  assert.match(source, /https:\/\/github\.com\/omarchy-forge\/omaudit/)
})

test('model independently rejects grades that JavaScript property lookup would coerce', () => {
  for (const grade of [[], ['A'], {}, null, false]) {
    const doc = clean()
    doc.plugins = [{id: 'x', name: 'X', version: '1', grade, score: 95, status: 'unchanged',
      firstParty: false, added: [], composition: [], evidence: {}}]
    doc.totals = {...Model.zeroTotals(), plugins: 1, unchanged: 1}
    doc.statusText = 'All tracked plugins unchanged'
    doc.worstGrade = Array.isArray(grade) ? String(grade) : ''
    assert.equal(Model.validateDocument(doc).valid, false)
  }
})

test('actual Python CLI to JS roundtrip rejects wrong grade types', () => {
  const dir = mkdtempSync(join(tmpdir(), 'omaudit-roundtrip-'))
  try {
    const row = JSON.parse(readFileSync(join(root, 'tests/fixtures/unchanged.json'), 'utf8'))[0]
    for (const grade of [null, false, {}, [], ['A'], 0, 'A', '']) {
      const input = join(dir, 'input.json'); writeFileSync(input, JSON.stringify([{...row, grade}]))
      const run = spawnSync(process.env.PYTHON || (process.platform === 'win32' ? 'python' : 'python3'),
        ['-B', join(root, 'scripts/status.py'), '--input', input], {cwd: dir, encoding: 'utf8'})
      assert.equal(run.status, 0, run.stderr)
      const result = Model.validateDocument(run.stdout)
      assert.equal(result.valid, true)
      assert.equal(result.document.ok, typeof grade === 'string', JSON.stringify(grade))
    }
  } finally {rmSync(dir, {recursive: true, force: true})}
})

test('Python and JavaScript agree on mixed BMP and supplementary plugin ID ordering', () => {
  const dir = mkdtempSync(join(tmpdir(), 'omaudit-order-'))
  try {
    const row = JSON.parse(readFileSync(join(root, 'tests/fixtures/unchanged.json'), 'utf8'))[0]
    const input = join(dir, 'input.json')
    const ids = ['\u{1F6E1}', '\uE000', 'a\u{1F6E1}', 'a\uE000', 'a']
    writeFileSync(input, JSON.stringify(ids.map(id => ({...row, id}))))
    const run = spawnSync(process.env.PYTHON || (process.platform === 'win32' ? 'python' : 'python3'),
      ['-B', join(root, 'scripts/status.py'), '--input', input], {cwd: dir, encoding: 'utf8'})
    assert.equal(run.status, 0, run.stderr)
    const result = Model.validateDocument(run.stdout)
    assert.equal(result.valid, true, result.document.error)
    assert.deepEqual(result.document.plugins.map(p => p.id), ['a', 'a\uE000', 'a\u{1F6E1}', '\uE000', '\u{1F6E1}'])
    const reversed = JSON.parse(run.stdout)
    reversed.plugins.reverse()
    assert.equal(Model.validateDocument(reversed).valid, false)
  } finally {rmSync(dir, {recursive: true, force: true})}
})

test('actual Python CLI to JS roundtrip accepts supplementary Unicode in every bounded field', () => {
  const dir = mkdtempSync(join(tmpdir(), 'omaudit-unicode-'))
  try {
    const row = JSON.parse(readFileSync(join(root, 'tests/fixtures/unchanged.json'), 'utf8'))[0]
    for (const count of [101, 200, 201]) {
      const input = join(dir, 'input.json')
      writeFileSync(input, JSON.stringify([{...row, id: '🛡'.repeat(count), name: '🛡'.repeat(count),
        version: '🛡'.repeat(count), composition: ['🛡'.repeat(301)], status: 'changed',
        added: ['🛡'.repeat(101)], evidence: {['🛡'.repeat(101)]: ['🛡'.repeat(256), 1]}}]))
      const run = spawnSync(process.env.PYTHON || (process.platform === 'win32' ? 'python' : 'python3'),
        ['-B', join(root, 'scripts/status.py'), '--input', input], {cwd: dir, encoding: 'utf8'})
      assert.equal(run.status, 0, run.stderr)
      const result = Model.validateDocument(run.stdout)
      assert.equal(result.valid, true, result.document.error)
      assert.equal(result.document.plugins[0].name, '🛡'.repeat(Math.min(count, 200)))
      assert.equal(result.document.plugins[0].evidence['🛡'.repeat(101)].file, '🛡'.repeat(255))
    }
  } finally {rmSync(dir, {recursive: true, force: true})}
})
