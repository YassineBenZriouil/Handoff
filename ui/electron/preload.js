const { contextBridge } = require('electron')

contextBridge.exposeInMainWorld('handoff', {
  version: '1.0.0'
})
