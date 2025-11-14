# 贡献指南 (Contributing Guide)

感谢您对 VideoScribe 的关注！我们欢迎各种形式的贡献。

## 如何贡献

### 报告 Bug

如果您发现了 bug，请：

1. 先在 [Issues](https://github.com/enhen3/VideoScribe/issues) 中搜索是否已有相同问题
2. 如果没有，创建新 issue 并包含：
   - 问题的详细描述
   - 复现步骤
   - 期望行为 vs 实际行为
   - 系统环境（macOS/Linux 版本、Python 版本）
   - 相关错误日志

### 提出新功能

如果您有新功能建议：

1. 在 [Issues](https://github.com/enhen3/VideoScribe/issues) 中创建 Feature Request
2. 描述清楚：
   - 功能的用途和价值
   - 可能的实现方式
   - 是否愿意参与开发

### 提交代码

#### 准备工作

1. **Fork 仓库**
   ```bash
   # 在 GitHub 上 fork 项目到你的账户
   ```

2. **克隆到本地**
   ```bash
   git clone git@github.com:YOUR_USERNAME/VideoScribe.git
   cd VideoScribe
   ```

3. **安装依赖**
   ```bash
   chmod +x install_requirements.sh
   ./install_requirements.sh
   ```

4. **创建新分支**
   ```bash
   git checkout -b feature/your-feature-name
   # 或
   git checkout -b fix/your-bug-fix
   ```

#### 开发规范

1. **代码风格**
   - 使用 Python 3.x 标准
   - 遵循 PEP 8 规范
   - 使用类型注解（Type Hints）
   - 添加必要的文档字符串

2. **命名规范**
   - 函数名：小写下划线 `process_video()`
   - 类名：驼峰命名 `VideoProcessor`
   - 常量：大写下划线 `MAX_WORKERS`

3. **注释**
   - 复杂逻辑必须添加注释
   - 使用中文或英文均可
   - 公开 API 必须有文档字符串

#### 提交代码

1. **确保代码质量**
   ```bash
   # 测试代码是否能运行
   python3 bilibili_auto_transcribe.py --help
   python3 creator_batch_export.py --help

   # 测试 GUI
   python3 bilibili_gui_transcriber.py
   ```

2. **提交更改**
   ```bash
   git add .
   git commit -m "功能描述

   详细说明改动内容和原因"
   ```

3. **推送到 GitHub**
   ```bash
   git push origin feature/your-feature-name
   ```

4. **创建 Pull Request**
   - 访问你 fork 的仓库
   - 点击 "New Pull Request"
   - 填写 PR 描述：
     - 改动内容概述
     - 相关 Issue 编号（如 `Fixes #123`）
     - 测试情况
     - 截图（如有 UI 改动）

#### Pull Request 检查清单

提交 PR 前请确认：

- [ ] 代码已在本地测试通过
- [ ] 新功能有相应的文档更新
- [ ] 遵循项目代码风格
- [ ] 没有引入新的依赖（如有必须在 PR 中说明）
- [ ] 提交信息清晰明确
- [ ] 已从最新的 main 分支更新

### 文档改进

文档改进同样重要！如果您发现：

- 文档中的错误或不清楚的地方
- 缺少的使用说明
- 可以改进的示例

请直接提交 PR 或创建 Issue。

## 开发流程

1. **选择任务**
   - 浏览 [Issues](https://github.com/enhen3/VideoScribe/issues)
   - 选择带有 `good first issue` 或 `help wanted` 标签的
   - 在 issue 中评论表明你要处理它

2. **开发**
   - Fork 并创建分支
   - 实现功能
   - 测试

3. **提交**
   - 创建 Pull Request
   - 等待 review
   - 根据反馈修改

4. **合并**
   - PR 被接受后会合并到 main

## 代码结构

```
VideoScribe/
├── utils.py                      # 核心功能模块
│   ├── 视频信息获取
│   ├── 字幕下载
│   ├── Whisper 转录
│   └── 并发处理逻辑
├── bilibili_auto_transcribe.py   # CLI 单视频处理
├── creator_batch_export.py       # CLI 批量导出
├── bilibili_gui_transcriber.py   # GUI 应用
├── install_requirements.sh       # 依赖安装
└── build_gui_app.sh             # macOS App 打包
```

## 版本发布

项目使用语义化版本号：`MAJOR.MINOR.PATCH`

- **MAJOR**: 不兼容的 API 变动
- **MINOR**: 向下兼容的新功能
- **PATCH**: 向下兼容的 bug 修复

## 行为准则

### 我们的承诺

为了营造开放和友好的环境，我们承诺：

- 使用友好和包容的语言
- 尊重不同的观点和经验
- 优雅地接受建设性批评
- 关注对社区最有利的事情
- 对其他社区成员表示同理心

### 不可接受的行为

- 使用性化的语言或图像
- 挑衅、侮辱/贬损的评论，人身攻击
- 公开或私下骚扰
- 未经明确许可发布他人的私人信息
- 其他在专业环境中被认为不适当的行为

## 获取帮助

如有疑问，可以：

1. 查看 [README.md](README.md) 和 [更新日志.md](更新日志.md)
2. 在 [Issues](https://github.com/enhen3/VideoScribe/issues) 中提问
3. 联系项目维护者

## 许可证

通过贡献代码，您同意您的贡献将在 [MIT License](LICENSE) 下发布。

---

再次感谢您的贡献！🎉
