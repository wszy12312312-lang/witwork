// 预加载脚本：万维文 WitWork 桌面版。
// 保持 contextIsolation 隔离，当前不向渲染进程暴露任何原生能力
// （原「莱茵终端」原生窗口等集成已移除）。
const { contextBridge } = require('electron');

// 预留安全桥接口位（如需将来暴露受控的原生能力，统一在此处登记）。
void contextBridge;
