const $ = id => document.getElementById(id);
let token, mode = 'export', busy = false, home, pickerTarget, pickerDirectory, lastLogs = '';
const paths = {export: {}, import: {}};
async function api(route, data = {}) {
  const response = await fetch('/api/' + route, {method: 'POST', headers: {'Content-Type': 'application/json', 'X-RepoBundle-Token': token}, body: JSON.stringify(data)});
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || 'Request failed');
  return result;
}
function showError(message) { $('error').textContent = message; $('error').hidden = !message; }
function setMode(next) {
  paths[mode] = {source: $('source').value, destination: $('destination').value};
  mode = next;
  const exporting = mode === 'export';
  $('source').value = paths[mode].source || '';
  $('destination').value = paths[mode].destination || '';
  $('export-mode').classList.toggle('selected', exporting);
  $('import-mode').classList.toggle('selected', !exporting);
  $('export-mode').setAttribute('aria-pressed', exporting);
  $('import-mode').setAttribute('aria-pressed', !exporting);
  $('workspace-label').textContent = exporting ? 'Export repository' : 'Restore bundle';
  $('headline').textContent = exporting ? 'Your repository, ready to travel.' : 'Bring your repository back.';
  $('subtitle').textContent = exporting ? 'Choose a repository and a destination. We’ll take care of the rest.' : 'Choose a bundle and an empty folder to restore its files.';
  $('mode-description').textContent = exporting ? 'Package a local repository into one portable, readable text file.' : 'Rebuild a repository from a previously exported text bundle.';
  $('direction').textContent = exporting ? 'LOCAL FILES → ONE BUNDLE' : 'ONE BUNDLE → LOCAL FILES';
  $('source').placeholder = exporting ? '/path/to/repository' : '/path/to/bundle.txt';
  $('source-label').textContent = exporting ? 'Repository folder' : 'Bundle file';
  $('destination-label').textContent = exporting ? 'Save bundle to' : 'Restore into';
  $('hint').textContent = exporting ? 'A timestamped .txt bundle will be created in this folder.' : 'Use an empty or new folder. Existing files will not be overwritten.';
  $('run').textContent = exporting ? 'Create bundle ↗' : 'Restore repository ↙';
  $('flow-source').textContent = exporting ? 'REPOSITORY' : 'TEXT BUNDLE';
  $('flow-destination').textContent = exporting ? 'TEXT BUNDLE' : 'REPOSITORY';
  showError('');
}
$('export-mode').onclick = () => setMode('export');
$('import-mode').onclick = () => setMode('import');
function render(state) {
  busy = state.status === 'running';
  document.body.classList.toggle('running', busy);
  for (const id of ['run', 'export-mode', 'import-mode', 'source', 'destination', 'browse-source', 'browse-destination']) $(id).disabled = busy;
  $('status').textContent = {idle: 'Ready', running: 'Running', completed: state.summary.errors ? 'Completed with errors' : 'Complete', failed: 'Failed'}[state.status];
  $('dot').className = 'online';
  $('ready').textContent = busy ? 'Processing files…' : 'Ready when you are';
  document.querySelectorAll('.stage').forEach((element, index) => element.classList.toggle('on', index === (busy ? 1 : state.status === 'completed' ? 2 : 0)));
  for (const key of ['files', 'text_files', 'binary_files', 'errors']) $(key).textContent = state.summary[key] || 0;
  const bytes = state.summary.bytes || 0;
  $('bytes').textContent = bytes >= 1048576 ? (bytes / 1048576).toFixed(2) + ' MB' : bytes >= 1024 ? (bytes / 1024).toFixed(1) + ' KB' : bytes + ' B';
  const serializedLogs = JSON.stringify(state.logs);
  if (state.logs.length && serializedLogs !== lastLogs) {
    lastLogs = serializedLogs;
    const atBottom = $('feed').scrollHeight - $('feed').scrollTop - $('feed').clientHeight < 30;
    $('feed').replaceChildren(...state.logs.map(message => {const node = document.createElement('div'); node.className = 'entry'; node.textContent = message; return node;}));
    if (atBottom) $('feed').scrollTop = $('feed').scrollHeight;
  }
  $('result').hidden = state.status !== 'completed';
  if (state.status === 'completed') $('output-path').textContent = state.summary.output_path;
  if (state.status === 'failed') showError(state.logs[state.logs.length - 1] || 'Operation failed');
}
async function poll() {
  try { render(await api('state')); }
  catch (error) { $('status').textContent = 'Disconnected'; $('dot').className = ''; $('run').disabled = true; showError('Dashboard connection lost. Keep setup_and_run.sh running and reload this page.'); }
  setTimeout(poll, 600);
}
$('job-form').onsubmit = async event => {
  event.preventDefault();
  if (busy) return;
  showError(''); $('run').disabled = true;
  try {
    await api('run', {mode, source: $('source').value.trim(), destination: $('destination').value.trim()});
    render(await api('state'));
  } catch (error) { showError(error.message); $('run').disabled = false; }
};
$('copy-path').onclick = async () => {
  try { await navigator.clipboard.writeText($('output-path').textContent); $('copy-path').textContent = 'Copied'; setTimeout(() => {$('copy-path').textContent = 'Copy path';}, 1500); }
  catch { showError('Could not copy automatically. Select and copy the output path above.'); }
};
async function browse(path) {
  $('picker-error').textContent = '';
  try {
    const data = await api('browse', {path}); pickerDirectory = data.path;
    $('picker-path').value = data.path;
    $('up').onclick = () => browse(data.parent);
    $('entries').replaceChildren();
    const chooseFile = pickerTarget === 'source' && mode === 'import';
    for (const entry of data.entries) {
      if (!entry.directory && !chooseFile) continue;
      const button = document.createElement('button');
      button.textContent = (entry.directory ? '▸  ' : '▤  ') + entry.name;
      button.onclick = () => { if (entry.directory) browse(entry.path); else {$(pickerTarget).value = entry.path; $('picker').close();} };
      $('entries').append(button);
    }
    if (!$('entries').children.length) $('entries').textContent = 'No matching files or folders here.';
    $('choose-folder').hidden = chooseFile;
  } catch (error) { $('picker-error').textContent = error.message; }
}
async function openPicker(target) {
  pickerTarget = target;
  $('picker-title').textContent = target === 'source' && mode === 'import' ? 'Choose a bundle file' : 'Choose a folder';
  $('picker').showModal();
  await browse(home);
}
$('browse-source').onclick = () => openPicker('source');
$('browse-destination').onclick = () => openPicker('destination');
$('close-picker').onclick = () => $('picker').close();
$('home').onclick = () => browse(home);
$('choose-folder').onclick = () => {$(pickerTarget).value = pickerDirectory; $('picker').close();};
$('path-form').onsubmit = event => {event.preventDefault(); browse($('picker-path').value);};
(async () => {
  try {
    const response = await fetch('/api/bootstrap');
    if (!response.ok) throw new Error('Cannot initialize dashboard');
    const config = await response.json(); token = config.token; home = config.home;
    $('source').value = config.cwd; $('destination').value = config.cwd;
    paths.import.destination = config.cwd + '/restored_repo';
    setMode('export'); poll();
  } catch (error) {showError(error.message);}
})();
