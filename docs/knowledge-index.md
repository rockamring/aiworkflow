# 知识索引策略

知识索引的目标是把代码、文档、规则和符号转成 Agent 可检索的上下文。当前实现是最小可运行版本，优先保证离线 mock 测试和 CLI 工作流闭环。

## 当前索引对象

- `File`：源码、配置、Markdown 等文件内容。
- `Symbol`：从代码中提取的类、函数、方法、表等符号。
- `Document`：项目文档、知识库文档、README 等。
- `Rule`：规则类文档，目前 `AGENTS.md` 会被识别为规则。

## 当前语言支持

- Python：使用标准库 `ast` 提取 class / function。
- C++：使用轻量正则提取 class / struct / enum / function。
- C#：使用轻量正则提取 class / struct / interface / enum / method。
- Lua：使用轻量正则提取 table / function。
- Markdown / YAML / JSON / JS / TS：进入文件和文档索引，部分通用符号使用轻量规则提取。
- `.uasset`：作为二进制资产占位进入索引，不解析资产内容。

## 当前搜索方式

当前 `SearchService` 复用 `GraphStore.search()`：

- Neo4j 模式从图谱中取最多 250 个候选节点后做轻量关键词打分。
- InMemory 模式用于测试和 mock 场景。
- 返回结果包含来源、类型、分数、标签和文本内容。

## 已知边界

- 没有 Embedding。
- 没有 BM25。
- 没有增量索引。
- 没有 clangd / Roslyn / tree-sitter 级别语义解析。
- 没有 UE Reflection、Blueprint Graph、Unity Asset Graph 或 Perforce Graph。
- `.uasset` 目前不可读语义，只保留路径和占位信息。

## 后续升级方向

- 引入 tree-sitter 作为多语言轻量 AST 基座。
- C++ 接入 clangd 或 Clang LibTooling，补全调用关系和类型信息。
- C# 接入 Roslyn，补全 Unity 工程符号索引。
- 增加 BM25 + Embedding + Graph + Recent 的 Hybrid Search。
- 为游戏项目加入 UE Reflection、Blueprint、Asset、Shader、Crash Symbol 等专属索引。
