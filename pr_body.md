## 类型
- [x] ♻️ 重构

## 变更概述
将手写 modal 统一迁移到 Radix Dialog，消除 `fixed inset-0 z-50` 手写模式。

## 变更内容
- 新增 InputDialog（Radix Dialog 输入弹窗）
- 新增 Modal（Radix Dialog 通用容器）
- 9 处手写 modal 迁移到共享组件
- 剩余 6 处复杂 modal（ChatConsole×2 等）后续做

## 日志/验证证据
```
$ tsc --noEmit -p tsconfig.web.json
0 new errors
```

Closes #415
