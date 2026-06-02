param(
    [string]$AppPath = "",
    [int]$DebugPort = 9230,
    [int]$TimeoutSeconds = 20
)

$ErrorActionPreference = "Stop"

$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
if (-not $AppPath.Trim()) {
    $AppPath = Join-Path $RepoRoot "frontend\release\win-unpacked\Project_R.exe"
}
$AppPath = (Resolve-Path $AppPath).Path

if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
    throw "Node.js is required for Electron smoke test."
}

$logPath = Join-Path ([System.IO.Path]::GetTempPath()) "project-r-electron-smoke-$DebugPort.log"
$probePath = Join-Path ([System.IO.Path]::GetTempPath()) "project-r-electron-smoke-$DebugPort.cjs"
Remove-Item -LiteralPath $logPath, $probePath -ErrorAction SilentlyContinue

$probeScript = @'
const http = require("http");

const port = Number(process.argv[2]);
const timeoutSeconds = Number(process.argv[3]);

function getJson(url) {
  return new Promise((resolve, reject) => {
    const request = http.get(url, (response) => {
      let data = "";
      response.on("data", (chunk) => { data += chunk; });
      response.on("end", () => {
        try {
          resolve(JSON.parse(data));
        } catch (error) {
          reject(error);
        }
      });
    });
    request.on("error", reject);
    request.setTimeout(2000, () => {
      request.destroy(new Error("Timed out waiting for Electron debug target."));
    });
  });
}

async function waitForPage() {
  const deadline = Date.now() + timeoutSeconds * 1000;
  let lastError = null;
  while (Date.now() < deadline) {
    try {
      const pages = await getJson(`http://127.0.0.1:${port}/json`);
      const page = Array.isArray(pages) ? pages.find((item) => item.type === "page") : null;
      if (page?.webSocketDebuggerUrl) {
        return page;
      }
    } catch (error) {
      lastError = error;
    }
    await new Promise((resolve) => setTimeout(resolve, 500));
  }
  throw lastError || new Error("Electron debug page was not available.");
}

function connectAndInspect(page) {
  return new Promise((resolve, reject) => {
    const ws = new WebSocket(page.webSocketDebuggerUrl);
    const pending = new Map();
    const events = [];
    let nextId = 1;

    function call(method, params = {}) {
      const id = nextId++;
      return new Promise((callResolve, callReject) => {
        pending.set(id, { resolve: callResolve, reject: callReject });
        ws.send(JSON.stringify({ id, method, params }));
      });
    }

    ws.onmessage = (event) => {
      const message = JSON.parse(event.data);
      if (message.id && pending.has(message.id)) {
        const callbacks = pending.get(message.id);
        pending.delete(message.id);
        if (message.error) {
          callbacks.reject(new Error(JSON.stringify(message.error)));
        } else {
          callbacks.resolve(message.result);
        }
        return;
      }
      if (message.method) {
        events.push(message);
      }
    };

    ws.onerror = reject;
    ws.onopen = async () => {
      try {
        await call("Runtime.enable");
        await call("Log.enable");
        await new Promise((waitResolve) => setTimeout(waitResolve, 1500));
        const result = await call("Runtime.evaluate", {
          expression: `({
            href: location.href,
            bodyText: document.body.innerText.slice(0, 500),
            rootChildCount: document.getElementById("root")?.childElementCount ?? -1,
            rootHTMLSample: document.getElementById("root")?.innerHTML.slice(0, 300) || null
          })`,
          returnByValue: true,
        });
        const logErrors = events
          .filter((entry) => entry.method === "Log.entryAdded" && entry.params?.entry?.level === "error")
          .map((entry) => entry.params.entry);
        ws.close();
        resolve({ value: result.result.value, logErrors });
      } catch (error) {
        ws.close();
        reject(error);
      }
    };
  });
}

(async () => {
  const page = await waitForPage();
  const inspection = await connectAndInspect(page);
  const fileAssetErrors = inspection.logErrors.filter((entry) =>
    entry.text?.includes("ERR_FILE_NOT_FOUND") || entry.url?.includes("file:///") && entry.url?.includes("/assets/")
  );
  const hasRenderedRoot = inspection.value.rootChildCount > 0 && inspection.value.bodyText.trim().length > 0;
  const passed = hasRenderedRoot && fileAssetErrors.length === 0;
  console.log(JSON.stringify({ passed, ...inspection, fileAssetErrors }, null, 2));
  process.exit(passed ? 0 : 1);
})().catch((error) => {
  console.error(error);
  process.exit(1);
});
'@

Set-Content -LiteralPath $probePath -Value $probeScript -Encoding UTF8

$process = $null
try {
    $process = Start-Process -FilePath $AppPath -ArgumentList @(
        "--remote-debugging-port=$DebugPort",
        "--enable-logging",
        "--log-file=$logPath"
    ) -PassThru

    & node $probePath $DebugPort $TimeoutSeconds
    if ($LASTEXITCODE -ne 0) {
        if (Test-Path -LiteralPath $logPath) {
            Get-Content -LiteralPath $logPath -Tail 80
        }
        throw "Electron package smoke test failed."
    }
} finally {
    if ($process -and -not $process.HasExited) {
        Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
    }
    Remove-Item -LiteralPath $probePath -ErrorAction SilentlyContinue
}
