const { app, BrowserWindow, session } = require('electron')
const { spawn } = require('child_process')
const path = require('path')

let engineProcess = null

function startEngine() {
  const isWin = process.platform === 'win32'
  const engineName = isWin ? 'handoff-engine.exe' : 'handoff-engine'
  const enginePath = app.isPackaged
    ? path.join(process.resourcesPath, 'engine', engineName)
    : path.join(__dirname, '../../engine/dist', engineName)

  engineProcess = spawn(enginePath)
  engineProcess.stdout.on('data', d => console.log('Engine:', d.toString()))
  engineProcess.stderr.on('data', d => console.error('Engine error:', d.toString()))
}

function createWindow() {
  const win = new BrowserWindow({
    width: 900,
    height: 600,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      nodeIntegration: false,
      contextIsolation: true
    }
  })

  if (process.env.NODE_ENV === 'development') {
    win.loadURL('http://localhost:5173')
    win.webContents.openDevTools()
  } else {
    win.loadFile(path.join(__dirname, '../dist/index.html'))
  }
}

app.whenReady().then(() => {
  session.defaultSession.setPermissionRequestHandler((_wc, permission, callback) => {
    callback(permission === 'media')
  })
  session.defaultSession.setPermissionCheckHandler((_wc, permission) => {
    return permission === 'media'
  })
  // Only spawn bundled engine in production — in dev, run Python engine manually
  if (app.isPackaged) startEngine()
  createWindow()
})

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit()
})

app.on('before-quit', () => {
  if (engineProcess) engineProcess.kill()
})
