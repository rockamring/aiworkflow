# AI Workflow 架构评审与改进计划

> 生成日期：2026-07-19
> 范围：当前架构分析 + 后续优化优先级 + UE 引擎索引策略 + 数据架构决策

---

## 一、架构评审结论

### 总体评价

**方向和核心洞察正确，架构分层工整有前瞻性，当前交付物更接近"高配 Context Pack 生成器"而非完整的 Agent OS。**

### 架构得分：8/10

| 维度 | 评价 | 关键风险 |
|---|---|---|
| 模块边界 | CLI → Prepare → Context/Search → GraphStore(Protocol) 分层清晰 | 前期抽象合理，但注意不要过度 |
| Agent Profile 结构化 | prompt_style + adapter + 权限 + timeout 统一契约，异构 Agent 可互换 | 后续字段膨胀时需保持简洁 |
| Run Store | JSONL 追加审计，无数据库依赖，MVP 务实选择 | 长期需考虑查询能力扩展 |
| CommandPolicy | 破坏性命令过滤，安全的第一道防线 | 后续需扩展到项目级权限、角色 |
| 可测试性 | InMemoryGraphStore + DryRunAdapter，离线可测 | 搜索的 mock 和真实行为差距大 |

### 核心问题

1. **搜索质量不足**：关键词匹配而非 BM25/Embedding，大代码库下不可用
2. **符号提取太浅**：UE 反射宏（UCLASS/UPROPERTY/UFUNCTION）完全丢失
3. **无增量索引**：每次 ingest 全量重建，对大项目不可接受
4. **缺少反馈闭环**：无法判断 context pack 是否有效
5. **Agent OS 定位与实际交付有预期落差**

---

## 二、项目定位与用户场景

### 解决的核心问题

UE/Unity 项目使用 AI Coding（Codex / Claude Code 等）时：
- 每次需大量沟通项目细节才能获得满意的结果
- AGENTS.md / CLAUDE.md 太笼统，仅适合项目认知，不适合功能开发或 Bug 定位
- 多人协作时 AI 编码行为不一致

### 解决思路

```text
项目代码 + 文档 → ingest（建立知识索引）
               → prepare（按 Query 检索 + 打包成 Context Pack）
               → 交给 AI Agent 使用
```

目标：**降低沟通成本、提升多人 AI 编码一致性。**

### 与行业对比

| 公司 | 做法 | 与你项目的相似点 |
|---|---|---|
| Google 内部 | 统一代码上下文平台，AI 是消费方 | 理念最接近，先有 Context 基础设施，再迭代替换 Agent |
| Sourcegraph Cody | 代码智能 + RAG | 搜索质量是核心壁垒，方向一致但搜索差距大 |
| Cursor | 更好的 IDE 内置上下文 | 嵌入 IDE 但独立于 Agent |
| GitHub Copilot | prompt 拼接 + API | 深度集成 IDE，不跨 Agent |

---

## 三、优化优先级路线图

### P0（立即做）

| 项目 | 目标 | 方案 | 预估工作量 |
|---|---|---|---|
| 搜索质量提升 | 切换到 BM25，支持大型代码库 | Neo4j Full-Text Index + CALL db.index.fulltext.queryNodes | 小（仅改约50行） |
| UE 反射符号提取 | 支持 UCLASS/UPROPERTY/UFUNCTION 索引 | 增强正则匹配 + 类继承关系写入图 | 中 |

### P1（下一个里程碑）

| 项目 | 目标 | 方案 | 预估工作量 |
|---|---|---|---|
| 增量索引 | 避免每次全量重建 | 记录文件 mtime + sha256，只 upsert 变化文件 | 中 |
| 搜索引擎独立 | 彻底解决搜索性能和质量 | 引入 Bleve / Tantivy 作为专用搜索索引层（磁盘文件 + mmap），Neo4j 退回到纯知识图谱角色 | 大 |

### P2（完善体验）

| 项目 | 目标 | 方案 | 预估工作量 |
|---|---|---|---|
| Embedding 语义搜索 | 支持自然语言 Query | sentence-transformers + hnswlib 向量索引 | 中 |
| 跨项目搜索 | 项目代码 + 引擎代码联合搜索 | SearchService 支持多 repo_id，项目结果加权 | 小 |
| 反馈回路 | 判断 context pack 是否有效 | agent run 记录 stdout/stderr；prepare 预览模式 | 中 |
| Agent Adapter 打通 | agent run 真正执行 Codex | 完善 CodexCliAdapter，让 prepare 到 agent run 自动化 | 中 |

### 不做（当前阶段不投入）

- 服务化拆分（K8S、消息队列）
- 完整 Tool Service 接入（Jira、Perforce 等）
- IDE 插件
- 自训练 Coding Model

---

## 四、UE 引擎索引策略

### 原则

**引擎索引一次，不得每项目重复索引。**

### 索引结构

```text
Repo A: UE_5.3（共享，只建一次）
  ├── /Engine/Source/Runtime/Core
  ├── /Engine/Source/Runtime/Engine
  └── /Engine/Source/Runtime/Renderer

Repo B: MyGame（每个项目独立）
  └── /Source/MyGame

Repo C: AnotherGame（每个项目独立）
  └── /Source/AnotherGame
```

### 搜索策略

```yaml
# config/workflow.yaml 配置示例
projects:
  my_game:
    repo: "D:/Projects/MyGame"
    extra_repos:            # 新增字段
      - "D:/UE_5.3/Engine/Source"
```

搜索时：主项目结果 × 1.5 权重 + 引擎结果 → 合并后取 top N。

### 为什么不合并索引

- 引擎代码量是项目的 10-20 倍，噪点过多
- 引擎和项目更新频率不同（引擎几乎不变）
- 搜索时更关注项目代码里的实际用法，而非引擎的原始定义

---

## 五、数据架构决策

### 当前方式（入库式）

```text
Neo4j 存储 File/Symbol/Document/Rule 节点
MATCH + LIMIT 250 → Python 侧关键词打分 → 返回
```

问题：大代码库下 LIMIT 250 覆盖不到相关内容，排名质量差。

### 推荐演进路径

#### 阶段一（短期）：Neo4j Full-Text Index

```cypher
CREATE FULLTEXT INDEX code_search IF NOT EXISTS
FOR (n:File|Document|Rule) ON EACH [n.content, n.path]

// 查询改为
CALL db.index.fulltext.queryNodes("code_search", $query)
YIELD node, score WHERE node.repo_id = $repo_id
RETURN node, score ORDER BY score DESC LIMIT $limit
```

- 依赖：Neo4j 内置 Lucene，无需新依赖
- 索引持久：Neo4j 磁盘，默认 Docker volume
- 查询时内存：Neo4j page cache 自动管理，不额外占应用内存
- 效果：从全文扫描变为倒排索引，查询性能指数级提升

#### 阶段二（中期）：独立搜索引擎 + Neo4j 知识图谱分流

```text
SearchService 路由：
├─ 全文搜索 → 专用索引引擎（Bleve/Tantivy）→ 磁盘文件 + mmap
└─ 知识图谱 → Neo4j（符号继承链、模块依赖、文档标签）

查询不要求全量内存加载，索引文件 mmap 后由 OS Page Cache 自动管理
```

| 度量 | 引擎（500万行） | 项目（30万行） | 文档 |
|---|---|---|---|
| 原文 | ~800MB | ~50MB | ~5MB |
| 倒排索引 | ~250MB | ~15MB | ~2MB |
| 索引构建 | 3-10 分钟 | 10-30 秒 | <5 秒 |
| 查询延迟 | <100ms | <50ms | <10ms |
| 查询时内存 | <50MB | <20MB | <5MB |

所有数据持久在磁盘，无需每次启动全量加载到内存。

#### 阶段三（长期）：Hybrid Search

```text
用户 Query
  ├── BM25（关键词匹配）
  └── Embedding（语义匹配）→ HNSW 向量索引
             │
       多路召回合并 → 重排序 → 最终 Top N
```

Embedding 模型加载约 200-400MB 内存（all-MiniLM-L6-v2），可接受。

---

## 六、已确定的架构假设

| 假设 | 说明 |
|---|---|
| 引擎与项目的 extra_repos 搜索加权 | 主项目结果 × 1.5 权重，引擎结果正常权重 |
| Neo4j Full-Text Index 作为短期方案 | 不改动架构，仅改 graph.py 的 search 实现 |
| 不引入新依赖做长短期共存 | 短期只依赖 Neo4j 自有功能，中期才引入独立搜索引擎 |

---

## 七、下一步行动事项

- [ ] P0: graph.py 搜索改为使用 Neo4j Full-Text Index
- [ ] P0: 增强 ingest.py 中的 C++ 符号提取，支持 UE 反射宏
- [ ] P1: 实现文件级增量索引（mtime + sha256）
- [ ] P1: 设计和引入独立搜索引擎层（Bleve / Tantivy + mmap 索引文件）
- [ ] P2: search.py 支持多 repo_id 搜索（主项目 + 引擎）
- [ ] P2: 打通 aiworkflow agent run 真正调用 Codex CLI
- [ ] P3: 添加 Embedding 语义搜索兜底

