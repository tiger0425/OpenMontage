# 05 — Stage 1 director: brief-director.md

**What to build:** 新建 `skills/pipelines/fabric-education/brief-director.md`，定义从用户输入（面料照片 + 名称、成分、克重）生成 `fabric_edu_brief` 的完整流程。

**Blocked by:** 03 (Pipeline manifest: fabric-education.yaml)

**Status:** ready-for-agent

- [ ] 遵循现有 `fabric-promotion/idea-director.md` 的 Step 化和格式模式
- [ ] Step 0: 读取全局知识库（`.retrospectives/knowledge_base.md` + `.retrospectives/fabric-education/`）
- [ ] Step 1: 用户输入接收（面料照片、名称、成分、克重）
- [ ] Step 2: 面料分析——Agent 分析面料类型、质感、织法、风格等（可引用 `visual_qa` 工具）
- [ ] Step 3: 信息追问——Agent 判断是否需要追问（如 `weave`、`finishing`、`season`），生成追问问题让用户回答
- [ ] Step 4: 知识深度评级（`basic` / `deep`）——基于面料类型的知识点丰富度判断
- [ ] Step 5: pitfall 识别——列出该面料常见的消费者误区/坑
- [ ] Step 6: 教育切入点建议——推荐此面料最适合讲的知识角度
- [ ] Step 7: 产出 `fabric_edu_brief` artifact，校验 schema
- [ ] 路径规范：所有路径带 `projects/{project_name}/` 前缀
- [ ] review_focus 落地：面料事实准确、pitfall 不虚构、深度评级合理
