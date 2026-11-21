const {contextBridge,ipcRenderer}=require('electron');
contextBridge.exposeInMainWorld('workbenchDesktop',{
 start:()=>ipcRenderer.invoke('workbench:start'),
 open:()=>ipcRenderer.invoke('workbench:open'),
 control:()=>ipcRenderer.invoke('workbench:control'),
});
