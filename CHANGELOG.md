# [0.6.0](https://github.com/14790897/MiQi/compare/v0.5.0...v0.6.0) (2026-07-13)


### Bug Fixes

* **bridge:** defer sandbox init to after ready signal to avoid first-install timeout ([#252](https://github.com/14790897/MiQi/issues/252)) ([1ffff20](https://github.com/14790897/MiQi/commit/1ffff20d959a076c1249111bfde31427ac487e49))
* **ci:** remove char limit on frequency field in issue validator ([#213](https://github.com/14790897/MiQi/issues/213)) ([7ef3832](https://github.com/14790897/MiQi/commit/7ef3832f5fb96c05e9c4bf410591843353428583))
* **ci:** remove unreliable UI keyword screenshot check from PR validator ([#217](https://github.com/14790897/MiQi/issues/217)) ([dba1dd0](https://github.com/14790897/MiQi/commit/dba1dd0ea8f1c12607b74ba9f0f0197e6028444a))
* **ci:** restore parallel E2E workers on CI ([#216](https://github.com/14790897/MiQi/issues/216)) ([fac1425](https://github.com/14790897/MiQi/commit/fac1425ae85a9775e9683710e5154937d3832fd9))
* **ci:** skip issue template validation for enhancement-labeled issues ([#227](https://github.com/14790897/MiQi/issues/227)) ([25d1c5f](https://github.com/14790897/MiQi/commit/25d1c5fdfd79e67707ca69a9fa895f411a2f68cd))
* **desktop:** address issue 230 ui defects ([#237](https://github.com/14790897/MiQi/issues/237)) ([965e6e6](https://github.com/14790897/MiQi/commit/965e6e6b8617894357e638f841033b4051a3b532))
* **desktop:** align dark mode surfaces ([#258](https://github.com/14790897/MiQi/issues/258)) ([43ae605](https://github.com/14790897/MiQi/commit/43ae60506aac94db5ff0cf32f7091112def129d5))
* **desktop:** prevent config.get polling storm that caused false bridge death ([#235](https://github.com/14790897/MiQi/issues/235)) ([f2e3ca5](https://github.com/14790897/MiQi/commit/f2e3ca5f56bce9b4667177d5b5e24b3a7d004afe))
* **desktop:** prevent streaming messages leaking across sessions ([#212](https://github.com/14790897/MiQi/issues/212)) ([#214](https://github.com/14790897/MiQi/issues/214)) ([797a772](https://github.com/14790897/MiQi/commit/797a77230f21a89f776762a8dcab7048d6fd254b))
* **runtime:** degrade get_turn on corrupted JSON columns ([#124](https://github.com/14790897/MiQi/issues/124)) ([7c8921c](https://github.com/14790897/MiQi/commit/7c8921c399add3f67ec4a8e07b411410f1b0a1a5))
* **sandbox:** per-session workspace isolation and race condition fixes ([#221](https://github.com/14790897/MiQi/issues/221)) ([#223](https://github.com/14790897/MiQi/issues/223)) ([4b65b4f](https://github.com/14790897/MiQi/commit/4b65b4f019bd4682dad37478d448f0eaf6e6b2ce))
* **wsl-e2e:** initialize WSL user + verify sandbox dirs after creation ([#222](https://github.com/14790897/MiQi/issues/222)) ([d03aa61](https://github.com/14790897/MiQi/commit/d03aa61b92c9738e99fe3aa3279e4fd256577dd6))


### Features

* **desktop:** add MiQi Logo splash screen on startup ([#220](https://github.com/14790897/MiQi/issues/220)) ([5ea782b](https://github.com/14790897/MiQi/commit/5ea782b2cf212ea528b59ab87e7dcd9c6ce6e204))
* **desktop:** add sandbox enable/disable toggle in settings UI ([#254](https://github.com/14790897/MiQi/issues/254)) ([fd14bb4](https://github.com/14790897/MiQi/commit/fd14bb469b46a2892ecac0fdee8a09c3493a9148))
* **desktop:** add settings hover animations ([#255](https://github.com/14790897/MiQi/issues/255)) ([6545af1](https://github.com/14790897/MiQi/commit/6545af122d5eb000178a1c289be25a13fd31bd10))
* **desktop:** replace app icon with Micro Era (微观纪元) brand logo ([#257](https://github.com/14790897/MiQi/issues/257)) ([5545e40](https://github.com/14790897/MiQi/commit/5545e40afdf44c08b35603db3189b531c3b1a053)), closes [#250](https://github.com/14790897/MiQi/issues/250)
* **papers:** add CORE API PDF source, download progress, and paper search result cards ([#211](https://github.com/14790897/MiQi/issues/211)) ([88a308d](https://github.com/14790897/MiQi/commit/88a308dad339f00dd8040f53bbe7c73999702600)), closes [#141](https://github.com/14790897/MiQi/issues/141)
* **providers:** add built-in model unlock flow ([#208](https://github.com/14790897/MiQi/issues/208)) ([c6b2b5b](https://github.com/14790897/MiQi/commit/c6b2b5b028aaf5c293cdff923529a67dc63fb807)), closes [#191](https://github.com/14790897/MiQi/issues/191) [#191](https://github.com/14790897/MiQi/issues/191)
* **sandbox:** auto-install WSL dependencies on first use ([#210](https://github.com/14790897/MiQi/issues/210)) ([5fc1c4f](https://github.com/14790897/MiQi/commit/5fc1c4fa15bd550226544ad3feb04f1af2b23ccd))
* **skills:** add mof-synthesis-price-agent skill ([a010fde](https://github.com/14790897/MiQi/commit/a010fde0d6896ca28f2c9ac4ac3a8e23ef166272))


### Reverts

* Revert "feat(providers): add built-in model unlock flow ([#208](https://github.com/14790897/MiQi/issues/208))" ([#225](https://github.com/14790897/MiQi/issues/225)) ([a006b8b](https://github.com/14790897/MiQi/commit/a006b8bbed8fca9127510a4819cae428bbb86d64))

# [0.5.0](https://github.com/14790897/MiQi/compare/v0.4.0...v0.5.0) (2026-07-10)


### Bug Fixes

* **approval:** permanent allowlist works cross-session and persists to disk ([#181](https://github.com/14790897/MiQi/issues/181)) ([77fade8](https://github.com/14790897/MiQi/commit/77fade879a5b8f995c5d091d4504df6bc8e66665)), closes [#180](https://github.com/14790897/MiQi/issues/180)
* **bridge:** defer running state until handshake completes ([3e31b21](https://github.com/14790897/MiQi/commit/3e31b21dfbc8acc7c6bace3ae9da6fb0ac51e380))
* **bridge:** remove dead event emitter adapter ([#150](https://github.com/14790897/MiQi/issues/150)) ([113eddb](https://github.com/14790897/MiQi/commit/113eddb359f45ee334ee020be54273af5ca674c6))
* **ci:** move concurrency to job level so quick and e2e run independently ([e6768b3](https://github.com/14790897/MiQi/commit/e6768b3414a8c706709d107d946440ace12bb4ce))
* **ci:** quick job checkout PR head on pull_request_target ([4818881](https://github.com/14790897/MiQi/commit/4818881789021330a0c8808f9b7406000292d39e)), closes [#186](https://github.com/14790897/MiQi/issues/186)
* **ci:** use head_ref in concurrency group to avoid PR collision ([77c16f3](https://github.com/14790897/MiQi/commit/77c16f31d6ad5f4ac15edae386a10b0a8fcf9bac))
* **desktop:** collapse repeated assistant turn replies ([#178](https://github.com/14790897/MiQi/issues/178)) ([f92f758](https://github.com/14790897/MiQi/commit/f92f758341ad7d94d493915d15e6406f2bf1bf91))
* **desktop:** collapse toolHint progress after final + e2e shared helpers ([#184](https://github.com/14790897/MiQi/issues/184)) ([25239a3](https://github.com/14790897/MiQi/commit/25239a3bc7de18c6a8499b326aa1cedd46d29ac4))
* **desktop:** track Office tool files in Task Assets panel via onFinal tool_calls ([#188](https://github.com/14790897/MiQi/issues/188)) ([e015a7d](https://github.com/14790897/MiQi/commit/e015a7d69605c1acf10692c9cae2597e23a39798))
* **execution:** guard approval detail sanitization depth ([#153](https://github.com/14790897/MiQi/issues/153)) ([8047052](https://github.com/14790897/MiQi/commit/8047052df330cf2fc96c5b41376ee760b6cd70c9))
* **execution:** persist apply_patch approval keys ([#148](https://github.com/14790897/MiQi/issues/148)) ([cdebfc1](https://github.com/14790897/MiQi/commit/cdebfc1546afdbf87aab6651485bba70ab66b695))
* **execution:** timeout hung hook callbacks ([#149](https://github.com/14790897/MiQi/issues/149)) ([f936f21](https://github.com/14790897/MiQi/commit/f936f217bd4bb4b44c370ee98d6043964cfa2940))
* keep approval bypass UI off by default ([#207](https://github.com/14790897/MiQi/issues/207)) ([b8d99c6](https://github.com/14790897/MiQi/commit/b8d99c6e0c8d1c9b83f426b436ac219b3dbcd539))
* otel tool span cleanup, fork events, compact param, reasoning complete ([#76](https://github.com/14790897/MiQi/issues/76)) ([4583b07](https://github.com/14790897/MiQi/commit/4583b0702e433117fca7ca4bb68d284ddbb92302)), closes [#65](https://github.com/14790897/MiQi/issues/65) [#67](https://github.com/14790897/MiQi/issues/67) [#68](https://github.com/14790897/MiQi/issues/68) [#69](https://github.com/14790897/MiQi/issues/69)
* **providers:** do not retry http 409 conflicts ([#147](https://github.com/14790897/MiQi/issues/147)) ([0760b84](https://github.com/14790897/MiQi/commit/0760b84a93c7df57e6f171bb0377caaebc6ee849))
* **runtime:** isolate subagent end hook failures ([#154](https://github.com/14790897/MiQi/issues/154)) ([dba8b67](https://github.com/14790897/MiQi/commit/dba8b67dcf6b164263dd8f27764f0c794793ec1c))
* **runtime:** replace deprecated coroutine checks ([#152](https://github.com/14790897/MiQi/issues/152)) ([b08cb1d](https://github.com/14790897/MiQi/commit/b08cb1d7ba299ceb3473bc505a4b031c2997b2ba))
* **runtime:** use rowid instead of item_id for deterministic history ordering ([465844c](https://github.com/14790897/MiQi/commit/465844c370475c65d435845581f763afa3987780))
* **skills:** reject trailing separators in plugin names ([#117](https://github.com/14790897/MiQi/issues/117)) ([be1fb6c](https://github.com/14790897/MiQi/commit/be1fb6ca38085ac7cb8ce05d2756c05a91ce1dda))
* **workspace:** support PDF viewing in workspace file viewer ([#189](https://github.com/14790897/MiQi/issues/189)) ([#196](https://github.com/14790897/MiQi/issues/196)) ([bb51bcd](https://github.com/14790897/MiQi/commit/bb51bcd2bfa3aeea12f5466f8ef07a5908615e01))


### Features

* add approval bypass controls ([#201](https://github.com/14790897/MiQi/issues/201)) ([37ac482](https://github.com/14790897/MiQi/commit/37ac4826d39908338e6b618e0422231cb4d9c719))
* **desktop:** clarify Provider verification status ([#190](https://github.com/14790897/MiQi/issues/190)) ([e7ebb09](https://github.com/14790897/MiQi/commit/e7ebb09b5b3bd97f15255689a3bf946486fb27c9))
* **documents:** add workspace Office tools ([#174](https://github.com/14790897/MiQi/issues/174)) ([d4588e0](https://github.com/14790897/MiQi/commit/d4588e021b3f87b723144e616399f5e941226903))
* **feature:** 简化 Desktop Setup Wizard 默认初始化流程 ([#159](https://github.com/14790897/MiQi/issues/159)) ([a34a01d](https://github.com/14790897/MiQi/commit/a34a01dcf1d02d93609dbf963e7154f511da305a))
* **log:** 全链路日志记录与查看功能 ([#134](https://github.com/14790897/MiQi/issues/134)) ([#161](https://github.com/14790897/MiQi/issues/161)) ([e4fcb63](https://github.com/14790897/MiQi/commit/e4fcb63fd9006f34b7ae430bb95010f5e6740b7f))
* merge develop into main (v0.5.0) ([b9ac4bc](https://github.com/14790897/MiQi/commit/b9ac4bc3c3a539c5681eb42f2000ded82926037a))
* **sandbox:** per-session file isolation for write/read/edit tools ([#192](https://github.com/14790897/MiQi/issues/192)) ([f3a4ad6](https://github.com/14790897/MiQi/commit/f3a4ad6923baed51a3e93d96ef72e2ef511b3a34)), closes [#182](https://github.com/14790897/MiQi/issues/182)
* **sandbox:** use real session_key and Windows path mapping ([#200](https://github.com/14790897/MiQi/issues/200)) ([1def65b](https://github.com/14790897/MiQi/commit/1def65b56ab3530390c03e7614ec6b36247e3b99)), closes [#199](https://github.com/14790897/MiQi/issues/199)

# [0.4.0](https://github.com/14790897/MiQi/compare/v0.3.0...v0.4.0) (2026-07-06)


### Bug Fixes

* **action:** AI 日志审核误将 Feature Request 判定为日志可疑 ([6152696](https://github.com/14790897/MiQi/commit/61526964fc777bffc401157edb86149f3fb1314c)), closes [#113](https://github.com/14790897/MiQi/issues/113)
* **action:** improve validation error messages with actual lengths ([c67647a](https://github.com/14790897/MiQi/commit/c67647abd533269130f1c3c86a90958ae0d90fc4))
* **action:** normalize API base URL ([a5c858d](https://github.com/14790897/MiQi/commit/a5c858d0b46128b52812d7e8f52c1b9443ee4d21))
* address CodeRabbit review comments - filter tabs, resize cleanup, dynamic title, Share Task disabled ([1dbbc24](https://github.com/14790897/MiQi/commit/1dbbc242e3c1f7736edd8d832a183de3b0071464))
* **agent:** agent.list returns empty when session not yet created ([9f7ab0d](https://github.com/14790897/MiQi/commit/9f7ab0dbc334b85f2e91a5ea9446974965bcf5fd))
* **agent:** correct tool-call message order in sub-agent loop ([2dc77bd](https://github.com/14790897/MiQi/commit/2dc77bd424615fa4b748007871e157329b384596)), closes [#43](https://github.com/14790897/MiQi/issues/43)
* Anthropic stream_chat, env key isolation, bare command approval ([f506201](https://github.com/14790897/MiQi/commit/f506201d6690709967ba15c90344b1f46cfb7642)), closes [#21](https://github.com/14790897/MiQi/issues/21) [#22](https://github.com/14790897/MiQi/issues/22) [#23](https://github.com/14790897/MiQi/issues/23)
* **app_server:** skip session auth for read-only session methods ([3865dc3](https://github.com/14790897/MiQi/commit/3865dc38a5910075c79be34a34ad28bc8c2859ed))
* **app:** add lock around session creation to prevent race ([be0a991](https://github.com/14790897/MiQi/commit/be0a991aa89de90c3136075abbdca5fc10d19e39)), closes [#17](https://github.com/14790897/MiQi/issues/17)
* **bridge,desktop:** return full config from permissions.get; merge with defaults on frontend ([1cbb293](https://github.com/14790897/MiQi/commit/1cbb293c8884cfb85d23da3261c7631dde4badec))
* **bridge:** accept thread_id in plan.get handler ([77c1458](https://github.com/14790897/MiQi/commit/77c145894567dc54846d1f970b8f078f0ee9bc5d)), closes [#10](https://github.com/14790897/MiQi/issues/10)
* **bridge:** add missing _get_session_manager() helper function ([d580f5e](https://github.com/14790897/MiQi/commit/d580f5eeab2806f1dcefcb5405bc14b038b17e1b)), closes [#11](https://github.com/14790897/MiQi/issues/11)
* **bridge:** add missing IPC handlers for agents, plan, permissions, plugins ([f74bee6](https://github.com/14790897/MiQi/commit/f74bee6572dc7448555d6874f820c313daff1c4c))
* **bridge:** await plugin discovery safely ([54ee7ee](https://github.com/14790897/MiQi/commit/54ee7ee02d7b4d75564dc2b44e8fdd38d8ad8d75))
* **bridge:** cancel old drain task before spawning new one for same session ([248a7d3](https://github.com/14790897/MiQi/commit/248a7d359482fe5836b8f276e5fd1634fc6ba9ce))
* **bridge:** correct orchestrator attribute name tool_registry → tools ([3473906](https://github.com/14790897/MiQi/commit/34739066e11284af4026de00dd20f643db387466))
* **bridge:** drain TurnCompleteEvent after AgentMessageEvent ([1077c33](https://github.com/14790897/MiQi/commit/1077c33d6359cfe96fb7918291fbfca645d0df7b))
* **bridge:** harden initialize handshake and capability validation ([6dbd651](https://github.com/14790897/MiQi/commit/6dbd65170d31c05d679b1932bedc71dd8bcfe07f))
* **bridge:** harden shutdown sequence and resource cleanup ([1e8b064](https://github.com/14790897/MiQi/commit/1e8b06449660eeaf4de2a403c7255ca69d8ded37))
* **bridge:** namespace bare session_key with client_id for registry lookup ([5e924d8](https://github.com/14790897/MiQi/commit/5e924d85577f2fbead35c82b9e876e4453c74ce9))
* **bridge:** pass raw session_key to create_session, not runtime_id ([ae707e5](https://github.com/14790897/MiQi/commit/ae707e59464fd1002af2c85a622a21114e473aa2))
* **bridge:** prevent chat send timeout race ([e5521fd](https://github.com/14790897/MiQi/commit/e5521fd47678460b555856ccdb810996a79494a4))
* **bridge:** prioritize uv over bundled executable ([8a81676](https://github.com/14790897/MiQi/commit/8a816768464a86f2f173ec111e22c84f1cad64c7))
* **bridge:** reject pending on error and add setTimeout error boundary ([69c4a11](https://github.com/14790897/MiQi/commit/69c4a11508d0a7f38f09b0072ba78713adb44272)), closes [#70](https://github.com/14790897/MiQi/issues/70) [#71](https://github.com/14790897/MiQi/issues/71)
* **bridge:** reject pending requests and reset state on restart ([b5eb424](https://github.com/14790897/MiQi/commit/b5eb424ff2bbd0141f17530bdbc5695b5d77fb9c)), closes [#47](https://github.com/14790897/MiQi/issues/47) [#48](https://github.com/14790897/MiQi/issues/48)
* **bridge:** replace startswith with Path.relative_to for path traversal protection ([e75a410](https://github.com/14790897/MiQi/commit/e75a410c69ebb65a8445112c6a2cc77108455a13))
* **bridge:** restore _redact_secrets helper; remove dead handler tests ([ee6ccd2](https://github.com/14790897/MiQi/commit/ee6ccd25caecfb5ca4650136320df0d16d745804))
* **bridge:** skip session pre-auth for chat.send — handler auto-creates sessions ([a7fa82f](https://github.com/14790897/MiQi/commit/a7fa82f7b562faa67ba05122647fd342c1d43377))
* **bridge:** subscribe client to session before draining chat events ([b4cb835](https://github.com/14790897/MiQi/commit/b4cb8359fefd8b6e349a69a9d33ed326294b93eb))
* **bridge:** sync vitest mock with ready-handshake and fix dual line-handler bug ([82128d1](https://github.com/14790897/MiQi/commit/82128d1e63b526b12e9f2c907199263a974f01aa))
* **bridge:** tie chat timeout tests to constants ([73c2339](https://github.com/14790897/MiQi/commit/73c2339f8a913138c830a1790341c3a9298c867b))
* **bridge:** use startswith check for session_key namespace ([cb8d8ec](https://github.com/14790897/MiQi/commit/cb8d8ec26c44aec714e72e84a2d97447a56c2027))
* **bridge:** wire AgentControl into SpawnTool so sub-agents register with agent list ([30af12c](https://github.com/14790897/MiQi/commit/30af12c571645e162df2ce7b40e02921d1b4aa75))
* **chat:** add timeout for thread start and await bridge readiness ([6ce3a15](https://github.com/14790897/MiQi/commit/6ce3a15c3137614593d014e1cc7b753df8639ba2))
* **chat:** allow sending when reveal animation is still running ([475f87d](https://github.com/14790897/MiQi/commit/475f87d0520d009dc6b4866a7f6cea459c00cc32))
* **chat:** show thinking spinner whenever streaming, not just after progress ([6b1c225](https://github.com/14790897/MiQi/commit/6b1c22505dcfcdf47e4ece30b3bc4dcec8cb2c5f))
* **chat:** silence raw runtime events in progress display ([e3f22ac](https://github.com/14790897/MiQi/commit/e3f22ac20767b611d75d5319794d40b38dd7fdd7))
* **chat:** use explicit white background for console header ([780005a](https://github.com/14790897/MiQi/commit/780005aa355f15a0d9c524d279a0730c9ebeed85))
* **ci:** deduplicate bot comments and relax validation ([1e89e5e](https://github.com/14790897/MiQi/commit/1e89e5e31d56fa54730401367e50e7bc85a7f2c1))
* **ci:** gate bwrap tests on availability ([6e20158](https://github.com/14790897/MiQi/commit/6e20158630c4187c020495a3143b25d51b23526b))
* **ci:** make bwrap job non-blocking and add test output options ([4e6ac61](https://github.com/14790897/MiQi/commit/4e6ac61e2c4181d90bc10f70211da8834bb2da20)), closes [#72](https://github.com/14790897/MiQi/issues/72)
* **cron:** correct _validate_schedule_for_add import path ([21f968f](https://github.com/14790897/MiQi/commit/21f968f35e3a7a7f73f107be67eb286b9fe0d815)), closes [#13](https://github.com/14790897/MiQi/issues/13)
* **desktop:** add afterEach ELECTRON_RENDERER_URL restore; update plan/47 wording ([2a75069](https://github.com/14790897/MiQi/commit/2a75069e29a1fc5b2fceffc024d187b5eee9fe50))
* **desktop:** address code review for session status toggle ([faed0b5](https://github.com/14790897/MiQi/commit/faed0b57f3976a5c93a91b845c4cb04f86b37cf7))
* **desktop:** eliminate duplicate progress events and blank lines ([2d67663](https://github.com/14790897/MiQi/commit/2d676632a34268cdec70a74cd814d47e3d3c7e82))
* **desktop:** handle TurnAbortedEvent as terminal, fix chat.abort auth ([d0ffc4a](https://github.com/14790897/MiQi/commit/d0ffc4a1c3d54d9528bb85bd70d8bef83c06247f))
* **desktop:** initialize bridge transport for alpha ([440daba](https://github.com/14790897/MiQi/commit/440daba63b2a540f907c71153f5e4a288d3a2af2))
* **desktop:** parse WSL uptime with explicit separator ([42a29ae](https://github.com/14790897/MiQi/commit/42a29ae0f87f3b9c75b384499ee6e6f0966beafa))
* **desktop:** remove empty assistant bubble before AI reply ([ce2195b](https://github.com/14790897/MiQi/commit/ce2195baae68973331bc330cc360b451b4df3afc)), closes [#109](https://github.com/14790897/MiQi/issues/109)
* **desktop:** resolve 4-phase bug fixes for Electron desktop app ([ab83517](https://github.com/14790897/MiQi/commit/ab835171ab030a7738d5bbbeb747afa0bb70baa0))
* **desktop:** second review — error envelope, single-channel, full typecheck, cleanup assertions ([859b206](https://github.com/14790897/MiQi/commit/859b206bc327fb4f8f946ec32642bd9b9162dcc7))
* **desktop:** streaming lifecycle, init cleanup, lifecycle tests, typecheck ([5f713b1](https://github.com/14790897/MiQi/commit/5f713b1072764cc9496d1bf158ccc7529af422ab))
* **desktop:** third review — single-channel error delivery, spy readline.close+watcher.close ([3e219be](https://github.com/14790897/MiQi/commit/3e219becc67eed3e3f2a5d2f5cb483aa560fd400))
* **diagnose:** use bold text instead of markdown headers ([2c74175](https://github.com/14790897/MiQi/commit/2c7417502d5ad21c5130f1fd290ae7731fb50369))
* **docs:** _resolve_output_path defaults allowed_dir=workspace when None ([3fd31f4](https://github.com/14790897/MiQi/commit/3fd31f49f445ce01c30c4ff76a3dbb17b0476537))
* **docs:** always pass _write_workspace as allowed_dir for office write tools ([35538ba](https://github.com/14790897/MiQi/commit/35538ba76d690e91414f0b7dcaa85bb703159501))
* **docs:** pass workspace/allowed_dir to office write tools at registration ([03b1e9b](https://github.com/14790897/MiQi/commit/03b1e9bd38f8438277c66a078dff0dfdcdd5a1b4))
* **e2e:** add --no-sandbox for CI environments ([69a8cf5](https://github.com/14790897/MiQi/commit/69a8cf5adf6870e2f54e7aa36bdeadf2b37fe252))
* **e2e:** exclude mock-bridge specs from electron project ([427288f](https://github.com/14790897/MiQi/commit/427288f7a1ceed1f52d5c0cf7067e5333c33a09b))
* **e2e:** pass --no-sandbox as CLI arg instead of appendSwitch ([2235299](https://github.com/14790897/MiQi/commit/22352998530623b955caf31ffeaadcf8997b7948))
* **e2e:** scope session marker checks to main area ([617135e](https://github.com/14790897/MiQi/commit/617135ef538127ca01c40465ee5d22f9bf4746ee))
* **e2e:** update tests for redesigned UI and improve reporting ([6c0dd86](https://github.com/14790897/MiQi/commit/6c0dd8693c82daf46fa6ca6bf8067c6764bf302b))
* **exec:** approval resolved terminal event coverage (Phase 31.4 fix) ([2f1f285](https://github.com/14790897/MiQi/commit/2f1f28522ea27a97f458574ea2d7dd01d65dc794))
* **exec:** orchestrator always injects SandboxSelection for exec tool ([4dddd6d](https://github.com/14790897/MiQi/commit/4dddd6d60254304875e1518f65a84c6a98ea52e7))
* **exec:** permanent allowlist key format aligned with _make_key (Phase 31.7) ([a9c893d](https://github.com/14790897/MiQi/commit/a9c893df1bd1ec3ec467e81487ff874cdf46c0ce))
* **execution:** harden PermissionEngine against shell injection and fail-open ([8e2b1de](https://github.com/14790897/MiQi/commit/8e2b1defcc585d6a4b56366c8fc2d9cb695b1bc6))
* **history:** handle JSONDecodeError in load_items ([fe710ec](https://github.com/14790897/MiQi/commit/fe710ecf01037f4563318fcf24715a74959b50d8)), closes [#44](https://github.com/14790897/MiQi/issues/44)
* **history:** wrap compaction in transaction for atomicity ([2142a6c](https://github.com/14790897/MiQi/commit/2142a6c6ddb821d762b83133339e5fec96f5afa3)), closes [#33](https://github.com/14790897/MiQi/issues/33)
* **ipc:** align protocol field names with app-protocol spec ([989735d](https://github.com/14790897/MiQi/commit/989735d1f205b05ce07b47a05aeef9d9e2d576b2)), closes [#45](https://github.com/14790897/MiQi/issues/45) [#46](https://github.com/14790897/MiQi/issues/46)
* **ledger:** eliminate dual-write and fire-and-forget for exec/approval events (Phase 31.8) ([fb0a089](https://github.com/14790897/MiQi/commit/fb0a089258ddb23ca0e536f206f15defdf7e46b6))
* **nav:** switch to chat view on session select ([5d691df](https://github.com/14790897/MiQi/commit/5d691df21a2e1fd90152823a8606349ef4cbf6b5))
* **paths:** preserve legacy data compatibility ([2fdc913](https://github.com/14790897/MiQi/commit/2fdc91303ba4b0487add8e27abc89c13517632fd))
* **permission:** categorize office doc write tools as file_write (Phase 31.7) ([badb8c0](https://github.com/14790897/MiQi/commit/badb8c0d547382f3be42e98224ba1a40e7e3a544))
* **permissions:** document global control-plane semantics + cross-client tests ([d074e2f](https://github.com/14790897/MiQi/commit/d074e2f2f1349a6ec1a0f8191a6ab8a7e014ef91))
* **phase46:** address review — py3.11 compat, symlink semantics, fuzzy root validation, docs ([f63e6b7](https://github.com/14790897/MiQi/commit/f63e6b7eeb9f651cdafee5b41dcceb02c67a4a3d))
* **phase48:** address Codex review — restore plan, correct docs/changelog, fix frozen test, clean EOF ([074aaa0](https://github.com/14790897/MiQi/commit/074aaa0d854a85d238240010de9c220238a55089))
* **phase48:** correct agent.md facts and document pre-existing failure ([b84a43c](https://github.com/14790897/MiQi/commit/b84a43c756de68eb5e75a37cf532cadfb090c342))
* **plan/52-followup:** distinguish missing vs unauthorized session in agent.list ([b22fcab](https://github.com/14790897/MiQi/commit/b22fcabd6bbe00fb5396f4e4deb22a86ec9cac88))
* **plugins:** validate installed plugin manifests deterministically ([b9d933d](https://github.com/14790897/MiQi/commit/b9d933d928124ec9049e6dc5edb9987a1a98f5c0))
* **protocol:** align app protocol generator formatting ([ab15ce9](https://github.com/14790897/MiQi/commit/ab15ce9dbfe451d27114ea168ef4a1558d914ae4))
* **protocol:** align app server specs with handler params ([7f8a2a9](https://github.com/14790897/MiQi/commit/7f8a2a9acf62cd3ea6d64ad7179cc0347c5a8612))
* **protocol:** allow empty dataBase64 and validate before runtime lookup ([b6b09dd](https://github.com/14790897/MiQi/commit/b6b09dd2adbef92edfda958e5c4d2fdce587527f))
* **protocol:** regenerate app-protocol.ts to match current generator ([7954995](https://github.com/14790897/MiQi/commit/7954995ed3f52cf5bd698341845af1992476acc6))
* **protocol:** reject string coercion for bool and number params ([52ab81f](https://github.com/14790897/MiQi/commit/52ab81fb5a94c89240432fe08b6fcb0be4d40fa5))
* **protocol:** update thread model tests for compatibility methods ([081b6cb](https://github.com/14790897/MiQi/commit/081b6cb895e77e864ad4ac8b6e51c9a175580bc4))
* **protocol:** update TS generator and tests for plugin skill contracts ([74e1ddb](https://github.com/14790897/MiQi/commit/74e1ddbc629646d4cce911eedc35d7addb8605e1))
* **protocol:** use fixed INVALID_PARAMS message to comply with audit rules ([f043d6f](https://github.com/14790897/MiQi/commit/f043d6fc1d2a2796cec96998c05d9bb1ad46eb8b))
* **protocol:** validate model provider params before state lookup ([c901f82](https://github.com/14790897/MiQi/commit/c901f822ea5ed94e8e2b1f097ed982764f1d2a24))
* **provider:** gate stream_options to direct OpenAI only ([a13e5f4](https://github.com/14790897/MiQi/commit/a13e5f4f06251ff194bee3ed74f5dd4a8a3df286)), closes [#12](https://github.com/14790897/MiQi/issues/12)
* **providers:** parse HTTP-date Retry-After header per RFC 7231 ([f81ae98](https://github.com/14790897/MiQi/commit/f81ae983db03e0e20f228ba8eb147839eb3fd620))
* **providers:** repair malformed stream tool-call args with json_repair ([23a7c2c](https://github.com/14790897/MiQi/commit/23a7c2ccfc8b2657c5a8c8bc4d922097f46dc76b))
* **providers:** sanitize error message in stream_chat, log full details internally ([57535cf](https://github.com/14790897/MiQi/commit/57535cf0c52782cef2ddeef3d4f4cb45bd2b4bea))
* **providers:** share tool args parsing ([7ca167f](https://github.com/14790897/MiQi/commit/7ca167f8cd56917d376cfc7330a771b0865de90c))
* **providers:** treat network 'not found' as transient, not invalid ([b482627](https://github.com/14790897/MiQi/commit/b48262787da7f858f79889b14c3c249fae4f0b82))
* **runtime:** add session_id scoping to history and thread runtimes ([4999bf5](https://github.com/14790897/MiQi/commit/4999bf54f0b481a6b99ed7a8b60029ce73e7594c))
* **runtime:** block dangerous env vars in workbench process exec ([5995480](https://github.com/14790897/MiQi/commit/5995480bb8aa2fbc1fe869dbef1d4401f1a3864e))
* **runtime:** classify tool success via structured status ([82a3e05](https://github.com/14790897/MiQi/commit/82a3e05e0965bf5b78fe95a2ca841b1355f1e0a3)), closes [#104](https://github.com/14790897/MiQi/issues/104) [#108](https://github.com/14790897/MiQi/issues/108)
* **runtime:** close ExperienceStore TraceStore SQLite connection on shutdown ([2ea88de](https://github.com/14790897/MiQi/commit/2ea88de6bd607cc9e78a74ea51bbd77568129f8d))
* **runtime:** close Phase 10 post-audit gaps ([4a561e3](https://github.com/14790897/MiQi/commit/4a561e3c8f8ec9e9511b96bfb3de9b4846713744))
* **runtime:** correct thread/list default sort order to newest-first ([d85d46d](https://github.com/14790897/MiQi/commit/d85d46d7074e887bdf933d5171bc6bc954ef91e2))
* **runtime:** default missing role in compaction instead of KeyError ([e04f0fe](https://github.com/14790897/MiQi/commit/e04f0feabbed94e63ee319c8f256b75f1a641b9d))
* **runtime:** enforce client-visible command process controls ([397e132](https://github.com/14790897/MiQi/commit/397e1327f8720b9edaec025b88dcac8467d9f6af))
* **runtime:** expand env blocklist with JVM, build tool, and git prefixes ([f68a64e](https://github.com/14790897/MiQi/commit/f68a64e3a4b9aec0dec77d0358bce4eeee7da16b))
* **runtime:** filter internal events from chat progress stream ([1b43914](https://github.com/14790897/MiQi/commit/1b43914361e952467d5deff443548819bd1404c3)), closes [#35](https://github.com/14790897/MiQi/issues/35) [#35](https://github.com/14790897/MiQi/issues/35)
* **runtime:** fix TurnRunner tool-call message ordering ([ceef938](https://github.com/14790897/MiQi/commit/ceef938adb7f4985938c28681c309c6a9b5d464b))
* **runtime:** handle missing DB/tables gracefully in stored reader ([e0a3f04](https://github.com/14790897/MiQi/commit/e0a3f04ad038ef5284de2fc2c056c5dfa4a63607))
* **runtime:** harden ConfigUpdate and ThreadCommand error paths with CommandRejectedEvent ([cd5a14f](https://github.com/14790897/MiQi/commit/cd5a14f67bce542cb0f7bd9c85e1d9b65f7a4c55))
* **runtime:** harden disableTimeout conflict semantics and use UUID internal handle IDs ([2e6b97b](https://github.com/14790897/MiQi/commit/2e6b97b5eb6da5d7b4cd774bfd1c1099a7c6cb28))
* **runtime:** harden image URL validation and restrict client settings overrides ([f854195](https://github.com/14790897/MiQi/commit/f8541951f6fffb99a841ace662fe4eb176bd9d17))
* **runtime:** harden Phase 42 shell command — projection, ledger, and cancel semantics ([a967f26](https://github.com/14790897/MiQi/commit/a967f26b8fe4e3a3bbc02ada1c1b2fa6ec896feb))
* **runtime:** harden plugin control-plane error paths ([669f80d](https://github.com/14790897/MiQi/commit/669f80d712a46f18b8df8ffa4c5765b088cb6370))
* **runtime:** harden thread scoping and tool-call history persistence ([1b14150](https://github.com/14790897/MiQi/commit/1b141505642dffe0c865eeb3b23c5ddebcd52804))
* **runtime:** harden workbench process cleanup semantics ([33ee22f](https://github.com/14790897/MiQi/commit/33ee22f0b0475ad26669eb0657a5b4c1fd968d41))
* **runtime:** maintain provider-visible HistoryRuntime in stored operations ([fe64816](https://github.com/14790897/MiQi/commit/fe648160dea329c41a2f13822c920140838fd197))
* **runtime:** make skills extra roots client scoped ([02a0681](https://github.com/14790897/MiQi/commit/02a0681b1a4fc09c272418a009218b09a137f5f4))
* **runtime:** Phase 14 follow-up — abort cancellation, concurrency, gateway migration ([4d78529](https://github.com/14790897/MiQi/commit/4d785295f285851b5ab4135efdc81acc7bf62503))
* **runtime:** Phase 14 follow-up v2 — pending queue, per-runtime lock, remove dead code ([4fad9fe](https://github.com/14790897/MiQi/commit/4fad9fee72298061ad41af30dd0ed3a5cd95a7b1))
* **runtime:** Phase 36 hardening — double-namespace, session routing, integration tests ([0bd38e2](https://github.com/14790897/MiQi/commit/0bd38e27662d6d4849f8ef6ee49184ee16934977))
* **runtime:** Phase 43 test-lifecycle hardening — eliminate bridge test cleanup warnings ([d47d327](https://github.com/14790897/MiQi/commit/d47d327c950bc89747fcffde067daa2d9cb961f9))
* **runtime:** prevent duplicate provider history on import round-trip ([ad03367](https://github.com/14790897/MiQi/commit/ad033678ab2ba38fe1394ff647ff62d9a84aa957))
* **runtime:** prevent duplicate reasoning text accumulation ([68f9ebf](https://github.com/14790897/MiQi/commit/68f9ebf3214faee30363afd88188e78af77e74a8))
* **runtime:** prevent turn handler tests from hot-looping drain tasks ([68e5f49](https://github.com/14790897/MiQi/commit/68e5f4936da0784d3478d3c4b9aac1881ac66256))
* **runtime:** replace hardcoded model='default' with provider default ([5052162](https://github.com/14790897/MiQi/commit/5052162c99035558f10cdf4ef3d937d8963d31c0)), closes [#14](https://github.com/14790897/MiQi/issues/14)
* **runtime:** sanitize error messages — log full exc, return safe messages ([d56defa](https://github.com/14790897/MiQi/commit/d56defa45c0b072e7ada10bb05fc7052a4f93d99))
* **runtime:** sanitize error messages in turn handlers ([c5d34bc](https://github.com/14790897/MiQi/commit/c5d34bc24f60c3ef38071e84a49b6ff7b5583a9a))
* **runtime:** send incremental reasoning delta and emit item/completed ([5f67479](https://github.com/14790897/MiQi/commit/5f674793215fa0df6fbcb24efb7cb666a92a20d0)), closes [#35](https://github.com/14790897/MiQi/issues/35) [#89](https://github.com/14790897/MiQi/issues/89) [#69](https://github.com/14790897/MiQi/issues/69)
* **runtime:** stop leaking raw exception into AppServerError message ([07b7d4a](https://github.com/14790897/MiQi/commit/07b7d4ace5e66337ca48b5218ae8d74540c4122b))
* **runtime:** use actual history rows for replay integrity; add debug/replay/turn metadata ([d82d193](https://github.com/14790897/MiQi/commit/d82d19361ef3b7bccb8ad8119bb71d7260b9266f))
* **runtime:** use persistent aiosqlite connections to eliminate thread-leak warnings; clarify AgentLoopCompat docs ([88374b4](https://github.com/14790897/MiQi/commit/88374b4c14b763a40f0c97b39e3d4978f48ca0ae))
* **runtime:** use public AppServer API for skills events ([7bb3e2f](https://github.com/14790897/MiQi/commit/7bb3e2ff9403bea8a88bf358f0fb1c4ee400899b))
* **runtime:** validate config update paths against dunder/private attribute injection ([4323813](https://github.com/14790897/MiQi/commit/4323813603fa516cc2e118623cfbb3001fad5fb1))
* **runtime:** validate marketplace control-plane inputs ([c03b233](https://github.com/14790897/MiQi/commit/c03b2331181150f143465b8413653b8037ff5cce))
* **runtime:** validate skills and hooks filesystem roots ([f067e2a](https://github.com/14790897/MiQi/commit/f067e2addbf4598a4628bb1710ba774228dca4b0))
* **runtime:** wire real ContextCompressor, add audit metadata, fix turn_id and failure path ([db28a51](https://github.com/14790897/MiQi/commit/db28a5154a66362d4acd68fa57c7f8d6d9dc3e52))
* **runtime:** wire RuntimeSession event_sink and clarify caller isolation ([0aa6111](https://github.com/14790897/MiQi/commit/0aa61118541c57476783934f28093ddb16fcd5d9))
* sandbox manager lock and agent_control model default ([5dcbd5d](https://github.com/14790897/MiQi/commit/5dcbd5ded35bb1e2cae83de33347f20c0d532f6e)), closes [#64](https://github.com/14790897/MiQi/issues/64) [#66](https://github.com/14790897/MiQi/issues/66)
* **sandbox:** auto-cleanup streaming handles on stop ([1864b0d](https://github.com/14790897/MiQi/commit/1864b0da5f4961a817220e83d3813d73d73bc9d2)), closes [#62](https://github.com/14790897/MiQi/issues/62)
* **security:** add FutureWarning to get_runtime_session without caller_id ([0191f35](https://github.com/14790897/MiQi/commit/0191f352339283d1776c19154a7b75649772d1fc))
* **security:** gate allow-prefix rules with metacharacter safety check ([5cf1378](https://github.com/14790897/MiQi/commit/5cf13786c7f6363210a9e4e844d7aa89c9a06cb6))
* **security:** harden sandbox key sanitization, error messages, and file paths ([8b85ea2](https://github.com/14790897/MiQi/commit/8b85ea2678359690dbbe365e46643c2878152d25)), closes [#49](https://github.com/14790897/MiQi/issues/49) [#50](https://github.com/14790897/MiQi/issues/50) [#18](https://github.com/14790897/MiQi/issues/18)
* **security:** prevent session cross-access and sanitize error messages ([2fd8958](https://github.com/14790897/MiQi/commit/2fd895811ffdba4126f3e6630a14dbc56dc96b04))
* **session:** address CR feedback — move assistant dual-write outside history_runtime block + log errors ([4f4a7c9](https://github.com/14790897/MiQi/commit/4f4a7c940bacefb4a36f5e3e151027a1fad66cdf))
* **session:** allow reading unowned sessions in sessions_get_handler ([3dc2586](https://github.com/14790897/MiQi/commit/3dc2586eb1116cbd106650883b7ce658966a943e))
* **session:** move _get_session_manager inside try/catch in handler, add restart E2E debug ([5042219](https://github.com/14790897/MiQi/commit/5042219da3aa096e649f57e72bf331e3b1539c64))
* **session:** sessions.get returns messages for active AppServer sessions ([8d4cf62](https://github.com/14790897/MiQi/commit/8d4cf629928ccedb83effbf69c868687849e1501)), closes [#105](https://github.com/14790897/MiQi/issues/105)
* **sessions:** guard against undefined messages in SessionExplorer ([f8bff9a](https://github.com/14790897/MiQi/commit/f8bff9ac4b21210fec71fddcd6ce8fca2c9fe22c))
* **session:** 修复新建对话后左侧列表不显示的问题 (fix [#34](https://github.com/14790897/MiQi/issues/34)) ([b6d2dc8](https://github.com/14790897/MiQi/commit/b6d2dc82f58177e8940799f237d256572205ecc3))
* show demo title when sessionTitle is a timestamp ([df165f0](https://github.com/14790897/MiQi/commit/df165f009c3d16eec41f62b887de1ca6e8723ff4))
* show live tool calls in chat ([d5281ae](https://github.com/14790897/MiQi/commit/d5281ae33c996f7c54410349ed6582583070a508))
* show tool-created files in task assets ([bf01c38](https://github.com/14790897/MiQi/commit/bf01c389c1b7cdb72a0b0efc474553c9564a7889))
* **skills:** add path traversal guards to create/upload/delete ([8a10adf](https://github.com/14790897/MiQi/commit/8a10adf7687dd7b7b61fc7e090f399f6497dcbbc))
* **task:** add ownership check in finally cleanup ([e165a64](https://github.com/14790897/MiQi/commit/e165a64d8d731059a23ec480eac074dc30c2ffac))
* **task:** emit TurnCompleteEvent on error path ([df73a38](https://github.com/14790897/MiQi/commit/df73a386e29c6715ad6b41dbea032f5a5cdaed76)), closes [#20](https://github.com/14790897/MiQi/issues/20)
* **task:** reuse existing cancel event for same thread ([7bf6eea](https://github.com/14790897/MiQi/commit/7bf6eeacbef9fa188ee3628e2adcdd9cc5d3ed67)), closes [#16](https://github.com/14790897/MiQi/issues/16)
* **test:** always clean up real bwrap sandbox ([d1cf38e](https://github.com/14790897/MiQi/commit/d1cf38e89cdf98b1d698d0ebeee7bb637548cc98))
* **test:** bootstrap writable pytest base temp ([6e208f1](https://github.com/14790897/MiQi/commit/6e208f186daedc9b27154b487b06aa8837e79be6))
* **test:** classify subprocess and sandbox tests accurately ([3edb80e](https://github.com/14790897/MiQi/commit/3edb80ee7d84d5e5d8f84e44a05d3254c65727c6))
* **test:** clean up automatic pytest base temp safely ([3587d86](https://github.com/14790897/MiQi/commit/3587d86924975049095f28452fd8669f5ba52bfe))
* **test:** close orphaned aiosqlite connections in test cleanup ([a4555e6](https://github.com/14790897/MiQi/commit/a4555e6c5d989e39fb666d33d23beb2e057b598c))
* **test:** make empty-reply regression actually exercise empty content ([f9eb229](https://github.com/14790897/MiQi/commit/f9eb22995768021908e12479becbdb4d7509f210))
* **test:** replace tee with cross-platform script ([949f7b3](https://github.com/14790897/MiQi/commit/949f7b3fc5c3e122ea89b672e234a5d9d355dbff))
* **test:** update selectors for redesigned UI ([2c5e681](https://github.com/14790897/MiQi/commit/2c5e6815f4af8d3023978139ae73b9e59fba79d1))
* **tools:** reject empty web tool inputs ([fc6708f](https://github.com/14790897/MiQi/commit/fc6708f3ba2e1339faae32ffba9cad9b5e29d61b))
* **tui:** escape user-controlled strings in Rich markup ([6e33033](https://github.com/14790897/MiQi/commit/6e330335c014e3182175cd2ae78777132f2b6059))
* **turn:** save assistant reply before steering continuation ([c73944a](https://github.com/14790897/MiQi/commit/c73944a20a7ad57e33d1ca15073b95b38c3636d0)), closes [#15](https://github.com/14790897/MiQi/issues/15)
* **xlsx:** close workbooks on recalc exception path ([4269ef5](https://github.com/14790897/MiQi/commit/4269ef55eb33fe798f1047bb968bc61a2857505e))


### Features

* add module skeletons for skills, context, documents, plan, tui ([29b6826](https://github.com/14790897/MiQi/commit/29b68264a73b7e30574b1a83bc2ac98fa406b6c1))
* **agent:** add dual-emit typed events in AgentLoop ([c31098f](https://github.com/14790897/MiQi/commit/c31098f92624710224ba83d830133ffb6dd48783))
* **agent:** wire ToolOrchestrator into AgentLoop tool execution path ([d96c371](https://github.com/14790897/MiQi/commit/d96c37189b94583c53e5326fd68137d8cdbe7015))
* **apply_patch:** add unified-diff patch tool (plan/54) ([4564bb9](https://github.com/14790897/MiQi/commit/4564bb9419a14c5a2f3cd6190462bf75dd6b2fe2))
* **approval_policy:** granular approval policy with AskForApproval modes (plan/50) ([a982dfc](https://github.com/14790897/MiQi/commit/a982dfc01e10b1be50bdba9284ce41bf19f30beb))
* **bridge:** add BridgeRuntimeLoop with persistent asyncio event loop ([d4a1c6f](https://github.com/14790897/MiQi/commit/d4a1c6f002dc8acb7d2dcb52bb8c71e502392c3e))
* **bridge:** add EventEmitter for typed event → IPC translation ([64147a2](https://github.com/14790897/MiQi/commit/64147a27682f593981767cba4f38bc827e556838))
* **bridge:** add permission bridge handlers ([4eb02c1](https://github.com/14790897/MiQi/commit/4eb02c1c81d4d4c60fd3f27cd43e2b09a2bf87ac))
* **bridge:** add plugin bridge handlers ([b4a70ee](https://github.com/14790897/MiQi/commit/b4a70ee159878c5f166f742d8e10bb2b5c0a86ea))
* **bridge:** enforce Codex-style initialize handshake and experimental API gate ([395f9dc](https://github.com/14790897/MiQi/commit/395f9dca10620352c1844fa1e4b64680cb9a2489))
* **bridge:** make client_id required, remove compatibility shim ([dd92350](https://github.com/14790897/MiQi/commit/dd9235000fd524f37f4374b290dbea62ed61dd89))
* **bridge:** migrate agent.list/get to AppServer, unify agent handler family ([820d485](https://github.com/14790897/MiQi/commit/820d485eb7c920508f46fc4e3a29a1595915cea3))
* **bridge:** migrate agent.spawn and agent.kill to AppServer path ([213af58](https://github.com/14790897/MiQi/commit/213af586a98c538cb5d21e5e1886de7fd7a8607c))
* **bridge:** migrate approvals.* handlers to AppServer with session scoping ([dbde0b6](https://github.com/14790897/MiQi/commit/dbde0b69d6127143e71f59d8c4b6449d1efc1be8))
* **bridge:** migrate chat.send and chat.abort to AppServer path ([0a8ea1a](https://github.com/14790897/MiQi/commit/0a8ea1a0603acd5cb7f90ead4e5a39993d6b74fd))
* **bridge:** migrate config.* handlers to AppServer with session propagation ([9bae933](https://github.com/14790897/MiQi/commit/9bae9339876ae56792b83cd0642b72796fb167f7))
* **bridge:** migrate sessions.* handlers to AppServer with runtime lifecycle ([b1aeba1](https://github.com/14790897/MiQi/commit/b1aeba17d811ed63b52e66743616b19767be0384))
* **bridge:** register Codex turn API handlers ([1475789](https://github.com/14790897/MiQi/commit/14757895473bbd6d4b92118f6b91bc46d7ac7291))
* **bridge:** register Phase 38 Codex config feature handlers ([0466200](https://github.com/14790897/MiQi/commit/0466200e3572d26ef72346114dc745bdc88a034a))
* **bridge:** register phase46 fs watch fuzzy APIs ([99872eb](https://github.com/14790897/MiQi/commit/99872eb542b8c4801450e9ab487bd3be95b32a82))
* **bridge:** register workbench process command APIs ([eb45b59](https://github.com/14790897/MiQi/commit/eb45b59605996b533c592a6026ca514c39f4c91d))
* **bridge:** wire EventEmitter into BridgeServer ([8dd3429](https://github.com/14790897/MiQi/commit/8dd34290029e176752904c9e4c637d2ba67a01e8))
* **bridge:** wire ToolOrchestrator and AgentControl into BridgeServer ([65d47a3](https://github.com/14790897/MiQi/commit/65d47a3c7a74c05e57bf36a6e165a5bf4cea978e))
* **bwrap:** add BwrapCommandHandle and run_command_streaming() API ([e09cfcb](https://github.com/14790897/MiQi/commit/e09cfcba3ce70817974e99fb4211ea67a2a0663c))
* **ci:** add AI log authenticity validation ([8e7e24a](https://github.com/14790897/MiQi/commit/8e7e24af93df5a93345f95711d57d9c3f743edf0))
* **context:** add ContextualFragment protocol, built-in fragments, and ThreadStore ([d5e6221](https://github.com/14790897/MiQi/commit/d5e6221508bdfc489f964fbd891faf684d16f4c7))
* **context:** wire SkillsManager into ContextBuilder ([bc865d9](https://github.com/14790897/MiQi/commit/bc865d9be1e6bfda9dae13d9ad6b1c106c7a351c))
* **desktop:** add agent status indicators to SessionExplorer ([3b5ad74](https://github.com/14790897/MiQi/commit/3b5ad747716f48ea49279f6498212e2935e51a7b))
* **desktop:** add AgentPanel, PlanTracker, and sidebar nav items ([9a15c37](https://github.com/14790897/MiQi/commit/9a15c374cbfb2d0b417e8059cb2269e644fd5c45))
* **desktop:** add category filter tabs to ApprovalsPage ([5acca49](https://github.com/14790897/MiQi/commit/5acca494e0302010a7c3fedad9f9231fb906f01e))
* **desktop:** add collapsible plan sidebar to ChatConsole ([8ecc6fe](https://github.com/14790897/MiQi/commit/8ecc6fe4b13f085f3f5355ac0a13ae7805ef793d))
* **desktop:** add inline tool progress to ChatConsole ([df4223e](https://github.com/14790897/MiQi/commit/df4223e31b5d8ed0d8866d243efb534318dffccd))
* **desktop:** add manual session status switching via context menu ([2d22d37](https://github.com/14790897/MiQi/commit/2d22d37c2f24f80b8bd30ddd42b914f4ba746050))
* **desktop:** add new IPC types and preload APIs for multi-agent, plan, permissions, plugins ([3f4de9d](https://github.com/14790897/MiQi/commit/3f4de9d210caef923ef2462d25fad59181cc4852))
* **desktop:** add page routing for agents, plan, permissions, plugins, approvals, sessions ([65567c3](https://github.com/14790897/MiQi/commit/65567c3d63d94c2809d54553f95d873cea5eaad5))
* **desktop:** add PermissionManager and PluginMarket pages ([63bcbfc](https://github.com/14790897/MiQi/commit/63bcbfc2f112710e798f7978162dc3c6ea0fda4a))
* **desktop:** add thread tabs to ChatConsole for multi-agent support ([6205f05](https://github.com/14790897/MiQi/commit/6205f059b493024201eb35ae50a6b6f11c4124e4))
* **desktop:** add typed app client wrapper ([9c164a6](https://github.com/14790897/MiQi/commit/9c164a61a7c4678a823b121682ee90400fae91cc))
* **desktop:** expose alpha workflow pages ([be41fc7](https://github.com/14790897/MiQi/commit/be41fc7d97818f953c13d2467783463a88cfc2e7))
* **desktop:** expose typed app client from bridge manager ([8321d9b](https://github.com/14790897/MiQi/commit/8321d9bccfa577560fcc6baa9138885bfec85c63))
* **desktop:** improve alpha diagnostics ([201a781](https://github.com/14790897/MiQi/commit/201a781ab0ede00df6730d1ce7454a8ca269fb5c))
* **doc-tools:** support path param fallback and add PPT e2e test ([db10ff1](https://github.com/14790897/MiQi/commit/db10ff1f5289c0c1040680b5e4e431a1fb8e57c5))
* **docs:** add workspace path enforcement to docx_write/pptx_write/xlsx_write ([bbac7df](https://github.com/14790897/MiQi/commit/bbac7df707f2b7f1d26c6adf6a96e8e274db7c20)), closes [#2](https://github.com/14790897/MiQi/issues/2)
* **documents:** add Office document read/write tools ([c63cddf](https://github.com/14790897/MiQi/commit/c63cddf33f9ecb678006a9e308a2be355d8988c0))
* **exec_policy:** implement declarative permission policy DSL (plan/49) ([8ad3bd6](https://github.com/14790897/MiQi/commit/8ad3bd690fcb61c41e4ef5b865f5138c0bd78865))
* **exec:** emit exec lifecycle events ([48953c0](https://github.com/14790897/MiQi/commit/48953c036dd3ecfd93d628b2729bb8b88cc6d4d7))
* **exec:** ExecTool consumes ToolOrchestrator SandboxSelection (Phase 31.2) ([a18d142](https://github.com/14790897/MiQi/commit/a18d14277b6ff579177bf85ee594ac31038d23ed))
* **exec:** inject sandbox selection for file mutation tools ([6d074ff](https://github.com/14790897/MiQi/commit/6d074ff1a710c530d5de8fec61fb1b06898a747d))
* **exec:** stdout/stderr streaming and subprocess cancellation (Phase 31.5-31.6) ([4cde36c](https://github.com/14790897/MiQi/commit/4cde36cf7a9c6100a500a7274b4ba3c6d8df8074))
* **exec:** tag user shell command events ([5ae169c](https://github.com/14790897/MiQi/commit/5ae169c909106695d390e8f077f7d9ab279f6f2d))
* **exec:** use bwrap streaming API in _execute_in_sandbox() ([fd93eb8](https://github.com/14790897/MiQi/commit/fd93eb87f062770b5dc25b076e70d25e4e638cd3))
* **execution:** add module skeleton for unified execution engine ([f3e0794](https://github.com/14790897/MiQi/commit/f3e07944f16444e3b0e989d4d5097a0f86c0185e))
* **execution:** add PermissionEngine with policy decision logic ([949dc3b](https://github.com/14790897/MiQi/commit/949dc3b035b15ea81e6c8bcff70c9ea05a2b37fb))
* **execution:** add SandboxPolicyEngine and HookRuntime ([cdd7ba6](https://github.com/14790897/MiQi/commit/cdd7ba61f9914223f8c58947b966edb153738b10))
* **execution:** add ToolOrchestrator with full approval→sandbox→execute pipeline ([eb3f82f](https://github.com/14790897/MiQi/commit/eb3f82f69a145649b3655b8a5c7b33592808ebee))
* **hooks:** complete lifecycle hook system (plan/51) ([22b0a25](https://github.com/14790897/MiQi/commit/22b0a2534b60a1419deda1e6be47edfa5cdcb08d))
* **ledger:** exec and approval lifecycle events recorded for replay (Phase 31.8) ([3bb6e4e](https://github.com/14790897/MiQi/commit/3bb6e4ed676ec041f43cd0c5fcf48d073126fd67))
* **paths:** add canonical miqi home resolver ([130d0f6](https://github.com/14790897/MiQi/commit/130d0f61a3c22252a7c18fc70fe5649ca28ff7c6))
* **plan/52:** add AgentGraphStore SQLite persistence for agent jobs and spawn edges ([837d395](https://github.com/14790897/MiQi/commit/837d3950f9e7d9e5dcf41be4fa8523a5c5e42c42))
* **plan/56:** provider resilience hardening for OpenAI + Anthropic ([5f0a481](https://github.com/14790897/MiQi/commit/5f0a481263f5f869729cae42f0925d3e60155182))
* **plan/57:** propagate provider errors as failed turns ([f5f4846](https://github.com/14790897/MiQi/commit/f5f4846a4eb816122a726f8a7422c21f8d69b603))
* **protocol:** add all event types — turn, stream, tool, approval, multi-agent, plan, system ([29e68b7](https://github.com/14790897/MiQi/commit/29e68b73a1d4d4307ea501ab2253231fb742304d))
* **protocol:** add app server method registry ([4481b61](https://github.com/14790897/MiQi/commit/4481b61aff3c47a401247a8f6d468fd855a8e158))
* **protocol:** add command/submission types and permission policy types ([3eb9970](https://github.com/14790897/MiQi/commit/3eb99706279172e4b702ec8e805d29138c7e5dd7))
* **protocol:** add EventSeverity and AgentStatus enums ([8230a83](https://github.com/14790897/MiQi/commit/8230a83790b344d29b641b2f27eafe58cba1a08b))
* **protocol:** add module skeleton and test stubs ([0538c52](https://github.com/14790897/MiQi/commit/0538c526a0cdeac8859b1f7c64ac5db6666efd33))
* **protocol:** add protocol compatibility snapshot builder ([c383679](https://github.com/14790897/MiQi/commit/c383679ef0cf500e084c053b3f2219142ac6f330))
* **protocol:** add thread lifecycle, config, and command rejection events plus future commands ([c10cfc9](https://github.com/14790897/MiQi/commit/c10cfc932a949281afdfff5fd92cabe04e0a6157))
* **protocol:** add typed app server envelopes ([8cbe898](https://github.com/14790897/MiQi/commit/8cbe89805f284ccdbb3373c275293e5e169c0a9b))
* **protocol:** add typed core request models ([4d14fe2](https://github.com/14790897/MiQi/commit/4d14fe2fd20c6bbf79db6e67b1b67bc756932796))
* **protocol:** add typed core result models ([cd4e740](https://github.com/14790897/MiQi/commit/cd4e740940ad536014f994d0f50abc2e394ab6fa))
* **protocol:** add typed filesystem request models ([8ada302](https://github.com/14790897/MiQi/commit/8ada302efc9be9a9a9ffd075e24d2cf36572cb60))
* **protocol:** add typed filesystem result and event models ([17d9082](https://github.com/14790897/MiQi/commit/17d908217cad5b09c90ee0a5e4d80a0c6740cd40))
* **protocol:** add typed plugin skill request and result models ([31130ae](https://github.com/14790897/MiQi/commit/31130ae3c06addc1e7878c15516aa4c7df86e5b2))
* **protocol:** add typed process request models ([f90f726](https://github.com/14790897/MiQi/commit/f90f72617284369869dee6a85f3cad47ff9a254f))
* **protocol:** add typed process result and event models ([a947b2c](https://github.com/14790897/MiQi/commit/a947b2cd64e8c1704ac94ae6e77a3bf8bef6b890))
* **protocol:** add typed session request and result models ([ecfe600](https://github.com/14790897/MiQi/commit/ecfe6000a8967d3a911f5bc8af49fa061a855a81))
* **protocol:** add typed thread request and result models ([c353f24](https://github.com/14790897/MiQi/commit/c353f249803b7db87d8065dfae0ce8c2740e6628))
* **protocol:** add typed turn request models ([c00be72](https://github.com/14790897/MiQi/commit/c00be7281097457608aac6865724b92095d8552a))
* **protocol:** attach method specs to app server ([5c9f2b2](https://github.com/14790897/MiQi/commit/5c9f2b215dee0d314f25178187befe8099200549))
* **protocol:** attach typed result and event schemas ([649b385](https://github.com/14790897/MiQi/commit/649b385eba2dc9bc398141e98f4a6a42457ff0c9))
* **protocol:** carry user shell command metadata ([8f8f03d](https://github.com/14790897/MiQi/commit/8f8f03da9a8ebe5e4c9cdb533a106b674f7807fc))
* **protocol:** derive params schemas from request models ([5b9e1b8](https://github.com/14790897/MiQi/commit/5b9e1b8175490971aa39516ba93e47c7d385f3a7))
* **protocol:** export app server catalog schema ([8e2ed22](https://github.com/14790897/MiQi/commit/8e2ed222d8e72f2c1fbc844a7012397a2b5e96c7))
* **protocol:** expose app server protocol catalog ([40ab88c](https://github.com/14790897/MiQi/commit/40ab88c26c133cab5db6693ad15c6a99bcd915aa))
* **protocol:** generate core capability contracts ([4476838](https://github.com/14790897/MiQi/commit/4476838ce09647541b93f4f5f97603886e08c030))
* **protocol:** generate plugin skill contracts ([d47ed9c](https://github.com/14790897/MiQi/commit/d47ed9c67691234da4d562f6705a80d381d86ba3))
* **protocol:** generate session contracts ([f2e3c9f](https://github.com/14790897/MiQi/commit/f2e3c9f3ce07f70aee8919826c0935ad2986b056))
* **protocol:** generate thread interface contracts ([15e221c](https://github.com/14790897/MiQi/commit/15e221cc09c09775e710bbd169fbe9f0bc2944db))
* **protocol:** generate typed app protocol types ([3ba8703](https://github.com/14790897/MiQi/commit/3ba87031fdea947c330e5ca6318654fbb81be03e))
* **protocol:** generate typed result and event contracts ([772b452](https://github.com/14790897/MiQi/commit/772b45221857227816056855121e47990d840845))
* **protocol:** support model-derived result and event schemas ([99c41b7](https://github.com/14790897/MiQi/commit/99c41b73b09647df7f473128fe1edddd90af6a31))
* **protocol:** type core app server method specs ([fcda191](https://github.com/14790897/MiQi/commit/fcda191e42abe2e3c1332adf65da1ad7ff3bb1cb))
* **protocol:** type core capability method specs ([84192ee](https://github.com/14790897/MiQi/commit/84192ee3f7d5909c03c4e0246e6242916e8065fc))
* **protocol:** type plugin skill method specs ([279bb04](https://github.com/14790897/MiQi/commit/279bb041c8eb3d2f25edcbf0276bc74ecdfd9904))
* **protocol:** type thread compatibility methods ([e3901d3](https://github.com/14790897/MiQi/commit/e3901d3756fe1d71dd606c9378522843dba0b384))
* **protocol:** validate and type session handlers ([ede78aa](https://github.com/14790897/MiQi/commit/ede78aa46ddc542144c82c320e602f598f366c6e))
* **protocol:** validate and type thread app handlers ([f9328e2](https://github.com/14790897/MiQi/commit/f9328e29cc5533028b2015e0cb599f3ce477feec))
* **protocol:** validate command exec handlers with typed params ([baaa44c](https://github.com/14790897/MiQi/commit/baaa44caa7194c8bef75025654c92f486f152ab5))
* **protocol:** validate core capability handlers with typed params ([d83e6b3](https://github.com/14790897/MiQi/commit/d83e6b37ae72ee0e57aadc9a2a71b4b99acb54d3))
* **protocol:** validate filesystem handlers with typed params ([19d8fef](https://github.com/14790897/MiQi/commit/19d8fef32d20348ff1cb15599b1bf2e054b4441d))
* **protocol:** validate plugin skill handlers with typed params ([a9cde20](https://github.com/14790897/MiQi/commit/a9cde20ca01d08c984f56728043a7314a5680617))
* **protocol:** validate process handlers with typed params ([dd9734f](https://github.com/14790897/MiQi/commit/dd9734f4f4fb6af3a8574b2c30be9e2d3653f4e8))
* **protocol:** validate turn handlers with typed params ([6920534](https://github.com/14790897/MiQi/commit/6920534354c5459087b4cd317cbc843b6cf619a4))
* **protocol:** validate watch and fuzzy handlers with typed params ([4189dbe](https://github.com/14790897/MiQi/commit/4189dbe4b2393705fd3b7de193188dd82f85a7be))
* **providers:** add streaming fallback contract ([86bc0fa](https://github.com/14790897/MiQi/commit/86bc0fa8c964563a80f8b27539603adbf0f02a35))
* **providers:** stream OpenAI-compatible responses ([f3efbc0](https://github.com/14790897/MiQi/commit/f3efbc00f267ff77ea86e398a8e4634d9fb4a9f3))
* **runtime:** add _run_agent() turn execution loop to AgentControl ([777eed4](https://github.com/14790897/MiQi/commit/777eed47ce925e6ec8e1dca074c38c4b94c03258))
* **runtime:** add AgentRegistry with 4 built-in agent types ([30bae61](https://github.com/14790897/MiQi/commit/30bae617572fcab40051c87aad6ccb9e10d76ac3))
* **runtime:** add AgentStateMachine with validated transitions ([19783f8](https://github.com/14790897/MiQi/commit/19783f8e0d8f1e4f90fd0d25fa06e32eaddf3aa5))
* **runtime:** add append-only ledger runtime ([74592d6](https://github.com/14790897/MiQi/commit/74592d679412546db730e995873cce03abb29adc))
* **runtime:** add AppServer client cleanup hooks ([30ba462](https://github.com/14790897/MiQi/commit/30ba462c6f8687c61d18c96fca2a4f659aef3cf8))
* **runtime:** add client capabilities and notification opt-out ([f587a79](https://github.com/14790897/MiQi/commit/f587a79ddc252522240eaffb13b9ebcf576814f5))
* **runtime:** add client-scoped file artifact path resolver (Phase 30.2-30.3) ([4b69632](https://github.com/14790897/MiQi/commit/4b69632d747153ca09fa920673b6356538b4d28c))
* **runtime:** add client-scoped stored runtime reader ([f6949e3](https://github.com/14790897/MiQi/commit/f6949e34700afc79eacfc600579d8afd77f1ff95))
* **runtime:** add client-scoped workbench process runtime ([3250354](https://github.com/14790897/MiQi/commit/3250354cd9ad354a5bcb8d5c13290c6857775417))
* **runtime:** add Codex compact and inject item handlers ([2fa2063](https://github.com/14790897/MiQi/commit/2fa20631a73a950d0d767e2334b8996cec7fee65))
* **runtime:** add codex fs app handlers ([8765838](https://github.com/14790897/MiQi/commit/8765838508592d288d09c61f83e1723efed307ee))
* **runtime:** add codex fs protocol helpers ([e96c23b](https://github.com/14790897/MiQi/commit/e96c23b81b41c5299f056d5211339025b7984cdd))
* **runtime:** add Codex thread shell command handler ([69715b5](https://github.com/14790897/MiQi/commit/69715b579450fbefba2aeb1cbf255e0d1f7b19fb))
* **runtime:** add Codex turn protocol helpers ([653d7bd](https://github.com/14790897/MiQi/commit/653d7bd40d8f6efdf9960038dbb5692dd4d48c34))
* **runtime:** add Codex turn start interrupt and steer handlers ([383e161](https://github.com/14790897/MiQi/commit/383e1614db5237e067cd1c0726a093f148fb5eda))
* **runtime:** add Codex-style command exec handlers ([33ff78e](https://github.com/14790897/MiQi/commit/33ff78e15de2b3605532ff51e648e4b3fa5a2810))
* **runtime:** add Codex-style config read and batch write ([1879c28](https://github.com/14790897/MiQi/commit/1879c28ecabe932867d2644ce1f624de55750437))
* **runtime:** add Codex-style experimental feature runtime ([7d719a1](https://github.com/14790897/MiQi/commit/7d719a1902ca9231a80e6cebce717441fc720aad))
* **runtime:** add Codex-style MCP status handlers ([beb1090](https://github.com/14790897/MiQi/commit/beb1090bc53ea20a5c6ffaa566cfe3426fc6da8f))
* **runtime:** add Codex-style model catalog and provider capabilities ([358df09](https://github.com/14790897/MiQi/commit/358df092e864189dcba9d5846a01560ed361fcbc))
* **runtime:** add Codex-style permission profile catalog ([9a98404](https://github.com/14790897/MiQi/commit/9a984044e86eb683809738e7e98870100145e82f))
* **runtime:** add Codex-style plugin and marketplace handlers ([c386e7b](https://github.com/14790897/MiQi/commit/c386e7b76744fbe7c71ed9e086bf201ebb438997))
* **runtime:** add Codex-style plugin protocol views ([39fb747](https://github.com/14790897/MiQi/commit/39fb747e3979b1d6bc17293bdaeb4cf8f258260a))
* **runtime:** add Codex-style process lifecycle handlers ([886734c](https://github.com/14790897/MiQi/commit/886734c92558ed6453e440bff78351d0d345fdf6))
* **runtime:** add Codex-style skills and hooks handlers ([07d4b3e](https://github.com/14790897/MiQi/commit/07d4b3e152d4d86e26fdfbbf8d30f397fcdde32c))
* **runtime:** add Codex-style thread AppServer handlers ([360090b](https://github.com/14790897/MiQi/commit/360090b86b7c40d03ddf7112acdccbab33dbc647))
* **runtime:** add Codex-style thread protocol projections ([ae90fd5](https://github.com/14790897/MiQi/commit/ae90fd58d7663d65c54acd9ffbe1ff333a72f970))
* **runtime:** add Codex-style thread rollback ([45570ee](https://github.com/14790897/MiQi/commit/45570ee4f75d3293a2a7efe6ca670fed1463e32f))
* **runtime:** add context compaction operation (CompactionResult, compact_thread, estimate_tokens) ([0c94f08](https://github.com/14790897/MiQi/commit/0c94f08d7bdbfa48b1fc61a7cb6fa83f86a84777))
* **runtime:** add deterministic plugin catalog runtime ([078c191](https://github.com/14790897/MiQi/commit/078c1915f68362b3236de4d2497e20ce7033bbdd))
* **runtime:** add deterministic replay documents ([c58132c](https://github.com/14790897/MiQi/commit/c58132cdc12f16721ae583972a61770b1b32dda1))
* **runtime:** add fs watch runtime and handlers ([a719914](https://github.com/14790897/MiQi/commit/a7199149d76a9ef9c303a8bcffefccdbd3ae3941))
* **runtime:** add fuzzy file search runtime and handlers ([a5d70c9](https://github.com/14790897/MiQi/commit/a5d70c9fd0c390b3000c33437df06b30fbe8cf6d))
* **runtime:** add initialize protocol projections ([84d3978](https://github.com/14790897/MiQi/commit/84d3978bf1da612f440261f798c300624da8c2b6))
* **runtime:** add InputQueue and AgentControl with lifecycle management ([5b33df9](https://github.com/14790897/MiQi/commit/5b33df9c810744b9577063875d60b781befdd441))
* **runtime:** add ledger fork and rollback helpers ([5cd4b42](https://github.com/14790897/MiQi/commit/5cd4b42fa0c441ed91cb526385d58c0577e550b5))
* **runtime:** add MCP runtime adapter ([2616cd1](https://github.com/14790897/MiQi/commit/2616cd1a67d240ee1e94529073e133faa58b0edf))
* **runtime:** add module skeleton for multi-agent runtime ([cc6dc70](https://github.com/14790897/MiQi/commit/cc6dc7099dd9970406322d8f24c63c5247d381ab))
* **runtime:** add persistent history runtime ([0362404](https://github.com/14790897/MiQi/commit/0362404b345c678343af439eb8be0ceab78a3935))
* **runtime:** add persistent thread runtime ([857d90e](https://github.com/14790897/MiQi/commit/857d90ef896128e3e157989589daf4663277e1ea))
* **runtime:** add replay debug protocol views ([03512cf](https://github.com/14790897/MiQi/commit/03512cf7f71381e1a96462bb5ed9df2cee3506fd))
* **runtime:** add runtime tool registry factory ([d3a8923](https://github.com/14790897/MiQi/commit/d3a89231df751f5c79c4f07716ea30646548cb49))
* **runtime:** add shared experimental api gate ([18e3c75](https://github.com/14790897/MiQi/commit/18e3c75812418e4521a60822be2d883ee4aa2491))
* **runtime:** add stored replay inspector ([c7436f5](https://github.com/14790897/MiQi/commit/c7436f5004cd7fed46c6821700cfae5ec61611a3))
* **runtime:** add stored-aware replay debug handlers ([d835465](https://github.com/14790897/MiQi/commit/d835465143d63382ff4ecf2a10d0453e16282aa6))
* **runtime:** add TurnContext, ThreadManager, and PlanTracker with plan tools ([f38336e](https://github.com/14790897/MiQi/commit/f38336e7c08e4e129deee51e785fb2481bc817b7))
* **runtime:** add workbench process snapshots and bounded history ([d03730a](https://github.com/14790897/MiQi/commit/d03730a685117021cd24e7e9052c7621f30a31f0))
* **runtime:** align command and process timeout/output-cap semantics ([e67bad1](https://github.com/14790897/MiQi/commit/e67bad1f5eb1536107d98928a45945360a5b7a0d))
* **runtime:** apply permission profile exec prefix rules ([e2284e7](https://github.com/14790897/MiQi/commit/e2284e704d42a0457771621204bc9f1ef7c2a8d8))
* **runtime:** auto-compact before large turns via context_limit_chars budget ([463aae1](https://github.com/14790897/MiQi/commit/463aae1df3263d8547475cf23680e7b2b46becd8))
* **runtime:** complete Phase 10 runtime follow-up ([e0ca7b5](https://github.com/14790897/MiQi/commit/e0ca7b5687ebacef963adda92df3ffd3d9d6df9c))
* **runtime:** copy provider history when forking threads ([ba6e815](https://github.com/14790897/MiQi/commit/ba6e815fb717faa61e7fb72afadf5f9c2808a839))
* **runtime:** emit Codex-style thread notifications ([ba78d0b](https://github.com/14790897/MiQi/commit/ba78d0b494c0b0dce85c79aa6784265c1984cf6a))
* **runtime:** emit CommandRejectedEvent for unsupported commands, eliminate not-yet-wired ([f7e9575](https://github.com/14790897/MiQi/commit/f7e95752ed7a278b1c5ce9acb09d8a0cbc465cc8))
* **runtime:** emit streaming assistant deltas from TurnRunner ([6a94a5c](https://github.com/14790897/MiQi/commit/6a94a5cf9e9b821749fb4ea7ac018aad991a1603))
* **runtime:** execute user shell commands through tool runtime ([7f51493](https://github.com/14790897/MiQi/commit/7f514931b374493adb547032c68c863f3dd664f5))
* **runtime:** export stored thread replay documents ([044dab8](https://github.com/14790897/MiQi/commit/044dab886cf1580efea12149b38bdd255807f29b))
* **runtime:** expose public replay timeline builders ([8c9b0ee](https://github.com/14790897/MiQi/commit/8c9b0ee642eb25cdefc7119c57c8bd92aace148c))
* **runtime:** expose workbench process state APIs ([d5f6b3b](https://github.com/14790897/MiQi/commit/d5f6b3b9a9f0c496c4e3675b1f555cb3c7f93f1c))
* **runtime:** handle user shell commands during active turns ([cc82103](https://github.com/14790897/MiQi/commit/cc8210373de49c6bd41d08b50e807f62e14471d2))
* **runtime:** implement Phase 11 session runtime core ([aaac115](https://github.com/14790897/MiQi/commit/aaac115c532a85b31df6540fb3197b3a223fc937))
* **runtime:** implement Phase 12 turn/tool/context runtime ([7e16c26](https://github.com/14790897/MiQi/commit/7e16c262783a0bb271ae34746d0191fb75be50ef))
* **runtime:** import stored thread replay documents ([3e164bb](https://github.com/14790897/MiQi/commit/3e164bbe1c7f976261b0995d05f86bf2c3e0363c))
* **runtime:** initialize persistent runtime stores on start ([c061acd](https://github.com/14790897/MiQi/commit/c061acd04be98759d6e329f7c612272258d0a077))
* **runtime:** let AppServer own background tasks ([b5dc1b3](https://github.com/14790897/MiQi/commit/b5dc1b36cb0ad6d585b6b9a05141089253f60ea1))
* **runtime:** migrate cron handlers to AppServer ([8013a50](https://github.com/14790897/MiQi/commit/8013a501d1d38b10aef4767a36d31a44b072b3f6))
* **runtime:** migrate diagnostic handler and finalize control-plane audit ([1a88103](https://github.com/14790897/MiQi/commit/1a8810361b769da6062df295306d63ca30c70108))
* **runtime:** migrate MCP handlers to AppServer ([a198a32](https://github.com/14790897/MiQi/commit/a198a32952ecff65f91f7a3d2c37e1e1df18e047))
* **runtime:** migrate memory and experience handlers to AppServer ([d8b5a6e](https://github.com/14790897/MiQi/commit/d8b5a6e3ad304a53c2285dc3cbff3adc5c070a43))
* **runtime:** migrate plugin handlers to AppServer ([0c56d15](https://github.com/14790897/MiQi/commit/0c56d15e931055a50f57f09db1c9800adc681b64))
* **runtime:** migrate provider channel and permission handlers to AppServer ([8bacbd9](https://github.com/14790897/MiQi/commit/8bacbd982696e48a3aa514fa10b16fb19a3d67bd))
* **runtime:** migrate skill handlers to AppServer ([db3dfd7](https://github.com/14790897/MiQi/commit/db3dfd742359013bc18aeaf4d8b55b406d4a2de0))
* **runtime:** mirror selected runtime events into ledger ([bfe8d93](https://github.com/14790897/MiQi/commit/bfe8d931ab5a5f90deb4721c59c113a7bdd68032))
* **runtime:** mirror user turns into ledger ([331a579](https://github.com/14790897/MiQi/commit/331a579527de4bf5847246e0b23d601bbfbae5cf))
* **runtime:** pass cancellation into tool execution ([af306e4](https://github.com/14790897/MiQi/commit/af306e461cc3dd9ef3b12f05f814e3f106cbc712))
* **runtime:** pass client_id from session_handlers to SessionManager ([3c64b09](https://github.com/14790897/MiQi/commit/3c64b0977a69f02d84e00129ab453777e861b50c))
* **runtime:** persist Codex-style thread metadata ([557b3e6](https://github.com/14790897/MiQi/commit/557b3e6f1d6f6506823cec4701bc07d89ec8f067))
* **runtime:** persist compacted replacement history ([f175e6b](https://github.com/14790897/MiQi/commit/f175e6b0b3e17fd8a51e8eb45f8f99091cc4aa18))
* **runtime:** persist turn history through task runner ([1e537ec](https://github.com/14790897/MiQi/commit/1e537ecd1d6b04a02ce7514c2a0564d500401abb))
* **runtime:** Phase 13 — Agent Jobs, Plugins, Permissions, expanded hooks ([9e3a1e2](https://github.com/14790897/MiQi/commit/9e3a1e20fc54e9d1e96c5467ef7f27f1c0e03c6f))
* **runtime:** Phase 14 — Frontends as RuntimeSession clients ([29109c5](https://github.com/14790897/MiQi/commit/29109c5f539c3c7108820a516e360abea007503f))
* **runtime:** project ledger history into Codex thread views ([2e3c549](https://github.com/14790897/MiQi/commit/2e3c54988ac6b0825752aa5437e4aa381b618571))
* **runtime:** project runtime events to Codex item events ([705f544](https://github.com/14790897/MiQi/commit/705f544566db490f28dc653e25c42786ff44e5ed))
* **runtime:** project stored threads from ledger rows ([457b32f](https://github.com/14790897/MiQi/commit/457b32fb2824642af20001a0fbb77ed754197645))
* **runtime:** project user shell command source ([8227627](https://github.com/14790897/MiQi/commit/822762701cd6411d1b00150b269650ed167dab60))
* **runtime:** read stored threads without live sessions ([119afeb](https://github.com/14790897/MiQi/commit/119afebda87afdfb1e33e95fb36480f86345b4a6))
* **runtime:** record streaming and tool items in ledger ([eb8ebea](https://github.com/14790897/MiQi/commit/eb8ebeac78e2e462127197bcec1c1779f20922e3))
* **runtime:** support Codex preallocated turns and steering ([557de38](https://github.com/14790897/MiQi/commit/557de380d8b6bc12ba3be3df11a6d073b6bbc1b3))
* **runtime:** support stored rollback and fork paths ([7ba1b9b](https://github.com/14790897/MiQi/commit/7ba1b9bff10e52d43878088ae4166329caf4ccf3))
* **runtime:** wire approval responses to orchestrator ([e2a0a96](https://github.com/14790897/MiQi/commit/e2a0a964c7ecd506e954ad93d8551e1a7f89d0a8))
* **runtime:** wire CompactCommand to ContextRuntime.compact_thread ([bebf7e6](https://github.com/14790897/MiQi/commit/bebf7e640c7a82914ffe79f9f72af0d21ef7c26e))
* **runtime:** wire config updates to SessionState ([8ab48f3](https://github.com/14790897/MiQi/commit/8ab48f3355025cc1366648515b4576a207c96ae2))
* **runtime:** wire ledger runtime into session services ([ed47073](https://github.com/14790897/MiQi/commit/ed47073fb05a7b5c368040602cb121731cc39754))
* **runtime:** wire session history services into RuntimeServices ([8422cc0](https://github.com/14790897/MiQi/commit/8422cc0e484ca76af7dc5df0f30eed61edf437d8))
* **runtime:** wire thread commands to ThreadRuntime ([fdaa389](https://github.com/14790897/MiQi/commit/fdaa3894dcd3fed69c5ca654c514fcc17baf74c2))
* **sandbox:** client-scoped sandbox namespace (Phase 30.5) ([0e06083](https://github.com/14790897/MiQi/commit/0e0608333c23bd6c36fa0b38b0cef5503be6f2f8))
* **sandbox:** disable NONE fallback for file mutation tools ([bb5a931](https://github.com/14790897/MiQi/commit/bb5a9310cd537e08542d863c04f9e59ece5756d1))
* **sandbox:** enforce restricted exec workspace and network policy ([b773116](https://github.com/14790897/MiQi/commit/b773116cffd67cc26b0d4428e5bd3c31eebc50d4))
* **sandbox:** harden LANDLOCK availability and exec fallback-to-NONE ([6d7f5bc](https://github.com/14790897/MiQi/commit/6d7f5bc1085426851fd3e5e7bc285bda185f8b89))
* **session:** add owner_client_id to SessionManager metadata schema ([a57a801](https://github.com/14790897/MiQi/commit/a57a801a715a2465ea3b1a26ea9f6c2b64d6fd1e))
* **sidebar:** add archive option and use first message as title ([5fc0e8c](https://github.com/14790897/MiQi/commit/5fc0e8c3df4a86ac876543b91206cdc4a558ebc1))
* **sidebar:** remove sessions nav and move MCPs to AI group ([58af6a6](https://github.com/14790897/MiQi/commit/58af6a6c67991f4f613106f3a53aec2d69703d2e))
* **skills:** add SkillsManager and PluginManager with pyyaml dependency ([1fc59ce](https://github.com/14790897/MiQi/commit/1fc59ce6f4247d6a6c3789b25169d55c1c7125ac))
* **tui:** add plan sidebar rendering and inline diff display ([992a03f](https://github.com/14790897/MiQi/commit/992a03fa6a32c6a9b4e424eabda607a1d799f70d))
* **tui:** add Textual-based TUI app skeleton ([8392c2e](https://github.com/14790897/MiQi/commit/8392c2e972a826a01b246b105ba6125849917f66))
* **tui:** enhance TUI with keybindings, runtime connection, and proper message routing ([a9263a4](https://github.com/14790897/MiQi/commit/a9263a4dd063722c411e7aae71980f31b133a802))
* **ui:** add collapsible nav groups to sidebar ([8a67432](https://github.com/14790897/MiQi/commit/8a674325c1afe5fa42851757e49e602d81b93b99))
* **ui:** glitch M logo, resizable panels, card redesign, matcha bg ([5c5e69d](https://github.com/14790897/MiQi/commit/5c5e69de7781929b6d87d38cfafeba68fba0ea89))
* **ui:** improve sidebar and chat styling ([170ab55](https://github.com/14790897/MiQi/commit/170ab551b21ffd9c3678e01811849d2251c4e93f))

# [0.3.0](https://github.com/14790897/MiQi/compare/v0.2.2...v0.3.0) (2026-06-30)


### Features

* **diagnose:** add diagnostic scripts for bug reports ([a38c1d1](https://github.com/14790897/MiQi/commit/a38c1d1a4a6836fe9e42d46f815920fb41160dfd))

## [0.2.2](https://github.com/14790897/MiQi/compare/v0.2.1...v0.2.2) (2026-06-29)


### Bug Fixes

* **ci:** add workflow_dispatch trigger ([4f4c0c1](https://github.com/14790897/MiQi/commit/4f4c0c150e272c24a91560369db3a82843875329))
* **ci:** exclude real-e2e from vitest, allow passWithNoTests ([4849a50](https://github.com/14790897/MiQi/commit/4849a503844557bc6908f7ba86f76b174e96d257))
* **ci:** increase electron test timeout to 5min ([07b6f12](https://github.com/14790897/MiQi/commit/07b6f1247a71cc8564c0473d60f7f843d147dcec))
* **ci:** remove HOME=/root to fix config.json path mismatch ([cd90fb3](https://github.com/14790897/MiQi/commit/cd90fb3025ccec247433a5fccca80f2b4dc4020b))
* **ci:** set headless: true for CI smoke tests ([0d8bfad](https://github.com/14790897/MiQi/commit/0d8bfad889fd078d6b24137adf06fc0053b0db05))
* **test:** separate vitest and playwright configs ([501c6b6](https://github.com/14790897/MiQi/commit/501c6b610ce7001d99f50aa905eb3622499621e9))

## [0.2.1](https://github.com/14790897/MiQi/compare/v0.2.0...v0.2.1) (2026-06-26)


### Bug Fixes

* **desktop:** add predev script to auto-install Python deps ([2e05e40](https://github.com/14790897/MiQi/commit/2e05e408acfa2dc11c077bf2b0bb8ac5cd35bb2f))

# [0.2.0](https://github.com/14790897/MiQi/compare/v0.1.19...v0.2.0) (2026-06-26)


### Bug Fixes

* **bridge:** handle stdin write errors gracefully ([b642627](https://github.com/14790897/MiQi/commit/b64262781314e35bfafc52363f5f21ab69723a59))
* **chat:** persist user message immediately so it survives session switch ([5498057](https://github.com/14790897/MiQi/commit/54980577226dc974841ddd6f24fbd74a81d14f8e))
* **chat:** scroll to bottom on session open ([2fce763](https://github.com/14790897/MiQi/commit/2fce763fd7d395b959789600e060717ad0aba16c))
* **desktop:** stop scroll jank — sidebar list reset & chat stream lock ([2644787](https://github.com/14790897/MiQi/commit/264478766b7a94c83f1b222920badae380d4b1bf))
* handle cross-thread safety and prevent duplicate messages ([44a77fc](https://github.com/14790897/MiQi/commit/44a77fc9133f27402f53669e0b90a23b3f00428d))


### Features

* **chat:** persist and render subagent results ([1cd30ec](https://github.com/14790897/MiQi/commit/1cd30ec1dea918f06bcbe5dadca61611950befb1))
* **desktop:** persist and restore last active session ([2545c40](https://github.com/14790897/MiQi/commit/2545c4087daea5a027b62e599a459609e25c399e))
* **subagent:** support background execution in desktop mode ([e71c92d](https://github.com/14790897/MiQi/commit/e71c92d83caffa66ccd4c0dac4696a1aae124e32))
* 添加 SLURM 技能支持 ([53f649e](https://github.com/14790897/MiQi/commit/53f649e70c6342ed6f6d1115099e86b77346f772))

# [0.2.0-dev.7](https://github.com/14790897/MiQi/compare/v0.2.0-dev.6...v0.2.0-dev.7) (2026-06-24)


### Bug Fixes

* **bridge:** handle stdin write errors gracefully ([b642627](https://github.com/14790897/MiQi/commit/b64262781314e35bfafc52363f5f21ab69723a59))

# [0.2.0-dev.6](https://github.com/14790897/MiQi/compare/v0.2.0-dev.5...v0.2.0-dev.6) (2026-06-24)


### Bug Fixes

* **chat:** scroll to bottom on session open ([2fce763](https://github.com/14790897/MiQi/commit/2fce763fd7d395b959789600e060717ad0aba16c))

# [0.2.0-dev.5](https://github.com/14790897/MiQi/compare/v0.2.0-dev.4...v0.2.0-dev.5) (2026-06-24)


### Bug Fixes

* **desktop:** stop scroll jank — sidebar list reset & chat stream lock ([2644787](https://github.com/14790897/MiQi/commit/264478766b7a94c83f1b222920badae380d4b1bf))

# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]

### Added (2026-06-23) — Plan 62: Turn API Typed Validation
- **Typed turn request models** (`miqi/runtime/turn_request_models.py`):
  - 5 Pydantic v2 `BaseModel` subclasses with `validation_alias` for camelCase/snake_case interop: `TurnStartParams`, `TurnInterruptParams`, `TurnSteerParams`, `ThreadCompactStartParams`, `ThreadInjectItemsParams`.
  - Legacy snake_case alias compatibility via `_with_aliases()` helper + `populate_by_name=True`.
  - Field validators for non-empty `threadId`, `turnId`, `expectedTurnId`, `clientUserMessageId`; model-level content validation for text input requirements.
  - `TURN_METHOD_PARAM_MODELS` lookup dict and `required_fields_for_model()` helper for catalog alignment.
  - `validate_turn_params()` converts Pydantic `ValidationError` and `TurnProtocolError` to `AppServerError(code="INVALID_PARAMS")`.
- **Typed validation at handler boundaries** (`miqi/runtime/turn_app_handlers.py`):
  - All 5 turn handlers now validate params BEFORE any runtime state mutation (turn reservation, session.submit, interrupt_turn, steer_turn, history/ledger writes).
  - Validation ordering: typed validate → check session auth → atomically reserve turn slot → validate thread exists → submit.

### Added (2026-06-23) — Plan 61: Typed App Server Protocol
- **Typed envelope models** (`miqi/runtime/app_protocol.py`): `AppServerRequest`, `AppServerResponse`, `AppServerSuccess`, `AppServerError` (Pydantic v2).
- **Protocol registry** (`miqi/runtime/protocol_registry.py`):
  - `MethodStability` enum: `stable`, `experimental`, `deprecated`, `legacy`.
  - `MethodScope` enum: `connection`, `session`, `thread`, `turn`, `process`, `filesystem`, `debug`.
  - `ProtocolMethodSpec` frozen dataclass with method name, stability, scope, description, params schema, result/error schemas.
  - `ProtocolRegistry` — in-memory registry with `add()`, `get()`, `methods()`, `to_catalog()`, `to_json_schema()` (JSON Schema Draft 2020-12).
- **31 typed protocol method specs** (`miqi/runtime/protocol_specs.py`): All AppServer methods now have typed `ProtocolMethodSpec` constants with accurate `required` fields matching real handler parameters.
- **Protocol catalog** (`miqi/runtime/app_server.py`):
  - `protocol/catalog` self-describing endpoint returning full method catalog.
  - `protocol/method_names` returning sorted method name list.
  - `protocol/schema` returning JSON Schema Draft 2020-12 export.
  - `register_method()` accepts optional `spec` parameter; all 9 handler registration files updated.

### Added (2026-06-22-23) — Plan 60: Trustworthy Test Baseline
- **Cross-platform test infrastructure**:
  - `pytest` markers: `self_managed_env`, `subprocess`, `sandbox`, `wsl`, `bwrap` for platform-dependent test classification.
  - `miqi/paths.py` — canonical `get_miqi_home()` resolver with `_LEGACY_HOME` fallback for backward compat.
  - GitHub Actions CI: `python-tests.yml` for cross-platform Python runtime tests.
- **Test isolation hardening**:
  - Writable pytest `basetemp` bootstrap; automatic cleanup in `tmp_path`-based fixtures.
  - Safe subprocess/sandbox test teardown (orphaned process cleanup, real bwrap sandbox cleanup).
  - Legacy data directory compatibility preserved (`~/.miqi` vs old `~/miqi` paths).
- **bwrap/WSL acceptance**: Criterion 10 (real Ubuntu/WSL bwrap) marked as **PENDING** — WSL not functional on this host.

### Added (2026-06-20-21) — Plans 48-59: Execution Hardening
- **Legacy AgentLoop removal** (Plan 48): `AgentLoop` class, `RuntimeAgentLoopCompat`, `configure_agent_orchestrator` retired. `RuntimeModelSettings` replaces `agent_loop` references. See Removed section below for migration notes.
- **Declarative permission policy DSL** (Plan 49): `miqi/execution/exec_policy.py` — permission profiles with allow/deny rules.
- **Granular approval policy** (Plan 50): `miqi/execution/approval_policy.py` — `AskForApproval` modes with category-based routing.
- **Lifecycle hook system** (Plan 51): `miqi/execution/hook_runtime.py` — complete before/after hook pipeline.
- **Agent graph store** (Plan 52): `miqi/runtime/agent_graph_store.py` — SQLite persistence for agent jobs and spawn edges.
- **Unified diff patch tool** (Plan 54): `miqi/agent/tools/apply_patch.py` — apply unified-diff patches to workspace files.
- **Provider resilience hardening** (Plans 56-57): OpenAI and Anthropic providers — retry with exponential backoff, error → failed turn propagation.
- **OTEL observability** (Plans 58-59): OpenTelemetry SDK integration (`miqi/observability/otel.py`) — span lifecycle, error terminal state handling.

### Added (2026-06-14-20) — Plans 31-47: Runtime Platform
- **AppServer runtime** (Plans 35, 39-47): Codex-style application server with `ClientSessionRegistry`, event subscription/fanout, typed dispatch, background task management, client/session isolation with TTL eviction.
- **Turn API** (Plan 41): `turn/start`, `turn/interrupt`, `turn/steer`, `thread/inject_items`, `thread/compact/start` handlers with preallocated turn reservation, Codex event projection, background drain tasks.
- **Replay debug** (Plan 40): Deterministic replay documents, stored-aware replay inspector, `replay/turns`, `replay/timeline`, `replay/messages` APIs.
- **Stored threads** (Plan 39): Ledger-backed thread import/export, rollback/fork support, store-aware reader.
- **Thread rollout** (Plan 36): Codex-style thread API — rollback, fork, metadata persistence, provider history copy, thread notifications.
- **Plugin/Skills/MCP ecology** (Plan 37): `plugin/*`, `skills/*`, `mcp/*` AppServer handlers with deterministic plugin catalog, skills create/upload/delete, MCP status runtime.
- **Config/Feature/Model profiles** (Plan 38): `config/*`, `model/*`, `feature/*` AppServer handlers — config read/batch write, model catalog with provider capabilities, feature runtime with experimental API gate.
- **Workbench processes** (Plans 43-44): `command/exec` and `process/*` handlers with env sanitization (blocklist), timeout/output-cap semantics, client-scoped process runtime, streaming stdin/stderr, PTY resize (marked experimental), process state APIs, bounded history snapshots.
- **Shell commands in turns** (Plan 42): User shell commands during active turns — `command/exec` from within turn context, event projection, ledger recording.
- **FS watch & fuzzy search** (Plan 46): `fs/watch`, `fs/unwatch` with polling-based file change detection; `fuzzyFileSearch/*` with two-tier scoring (substring ≥1000, subsequence ≥500), session-based search.
- **Initialize handshake** (Plan 45): Codex-style `initialize` with client capabilities negotiation, notification opt-out, experimental API gate.
- **Desktop alpha release** (Plan 47): Internal alpha smoke checklist, alpha diagnostics, workflow pages, bridge transport initialization, desktop error handling.

### Added (2026-06-10-14) — Plans 9-30: Runtime Core
- **Runtime protocol & events** (Plan 9-10): Typed event system — turn, stream, tool, approval, multi-agent, plan, system events; command/submission types; permission policy types.
- **Session runtime** (Plan 11): `RuntimeSession` core with caller isolation, event sink, session cross-access prevention.
- **Turn/Tool/Context runtime** (Plan 12): `TurnRunner` with LLM calling loop, `ContextBuilder` for context injection, tool-call message ordering.
- **Multi-agent runtime** (Plan 13-14): `AgentRegistry` with 4 built-in types, `AgentStateMachine` with validated transitions, `InputQueue`, `AgentControl` with lifecycle, `ThreadManager`, `PlanTracker`, frontend-as-RuntimeSession-client.
- **Execution engine** (Plans 15-34): `ToolOrchestrator` with approval→sandbox→execute pipeline, `PermissionEngine`, `SandboxPolicyEngine`, `HookRuntime`. Per-session bwrap sandbox isolation with FIFO eviction (max 10), LANDLOCK file system ruleset, streaming stdin/stderr, subprocess cancellation. Office document read/write tools (docx, pptx, xlsx) with workspace path enforcement.
- **History & Ledger** (Plans 23-25): Persistent `HistoryRuntime` and `LedgerRuntime` with SQLite/aiosqlite; turn/streaming/tool/exec/approval event mirroring into append-only ledger; ledger-history comparison acceptance tests.
- **Frontend migration** (Plans 26-30): Bridge handlers migrated to AppServer — `chat.send/abort`, `agent.spawn/kill`, `sessions.*`, `config.*`, `approvals.*`, `agent.list/get`; `BridgeRuntimeLoop` with persistent asyncio event loop; client-scoped sandbox namespace; session ownership model (`owner_client_id`).
- **Desktop & TUI** (June 10): Electron desktop: 15 feature pages (Agents, Plan, Permissions, Plugins, Approvals, Sessions, Settings, Cron, Channels, Experience, MCPs, Memory, Provider, Skills, Workspace). Textual-based TUI app skeleton. Collapsible plan sidebar, thread tabs, agent status indicators, inline tool progress, category filter tabs.

### Added (2026-06-08)
- **Collapse tool call messages in chat**: Collapse tool call messages for cleaner conversation view.
- **Per-session bwrap sandbox isolation** (`miqi/sandbox/manager.py`): FIFO-based sandbox eviction policy (max 10).

### Removed (2026-06-20)
- **Legacy AgentLoop module and imports** (`miqi/agent/loop.py`):
  - Removed the `AgentLoop` class and `miqi/agent/loop.py` module. The `miqi/agent/__init__.py` no longer exports `AgentLoop`.
  - Removed `RuntimeAgentLoopCompat` and `RuntimeServices.agent_loop` property; replaced by `RuntimeModelSettings`.
  - Removed `configure_agent_orchestrator` from `miqi/execution/factory.py`.
  - All `services.agent_loop` references replaced with `services.model_settings` across the codebase.
  - **Public Python API break**: code that directly imported `AgentLoop` from `miqi.agent` or accessed `RuntimeServices.agent_loop` / `RuntimeAgentLoopCompat` must migrate to `RuntimeModelSettings`.
  - **Intentional retirement** of unreachable AgentLoop-only behaviors including `_run_agent_loop`, `_call_llm_for_summary`, `_register_default_tools`, and `flush_if_needed` instance methods. These behaviors are explicitly retired, not migrated: `_run_agent_loop` was replaced by `TurnRunner`, `_call_llm_for_summary` by `ContextRuntime`, and `_register_default_tools` by `ToolRegistryFactory` during earlier phases. `flush_if_needed` is retired without a direct replacement; a runtime nudge mechanism does not yet exist.

### Added (2026-06-08)
- **Collapse tool call messages in chat**:
  - Added ability to collapse tool call messages in chat interface for cleaner conversation view
- **Per-session bwrap sandbox isolation** (`miqi/sandbox/`):
  - Added `manager.py` with FIFO-based sandbox eviction policy (max 10 sandboxes) for per-session bwrap isolation
- **Docs tab to Settings page**:
  - Added documentation tab to settings page for easy access to project documentation

### Added
- **KUN runtime migration — Bridge server integration**:
  - Modified `miqi/bridge/server.py` `BridgeState` to support KUN runtime:
    - Added `runtime_mode` field (initialized from `config.agents.defaults.runtime`, values `"legacy"` or `"kun"`).
    - `build_agent()` now reads runtime mode: when `"kun"`, creates a `GatewayKunRuntime` instead of legacy `AgentLoop`.
    - Extracted `_build_tool_registry(config)` helper function for shared ToolRegistry construction (filesystem/shell/web/papers).
    - `load_config()` auto-updates `runtime_mode` from config.
    - Bridge startup logs `Runtime mode: legacy` or `Runtime mode: kun`.
  - Modified `miqi/kun_runtime/migration_adapter.py` `GatewayKunRuntime`:
    - Added `_abort_event` (threading.Event) for compatibility with bridge's `abort_active()` / `handle_chat_send` abort logic.
  - No changes to bridge protocol, stdin/stdout JSON-line format, or frontend code.
  - All tests pass: 447 total (103 original + 344 new).

- **KUN runtime migration — Phase 10 (CLI/Gateway Integration)**:
  - Added `runtime` field to `AgentDefaults` config (`agents.defaults.runtime`, default `"legacy"`).
  - In `miqi/cli/gateway_cmd.py`: when `runtime == "kun"`, wire a `GatewayKunRuntime` as the agent instead of the legacy `AgentLoop`.
  - In `miqi/cli/agent_cmd.py`: same runtime-switch logic for both one-shot (`-m`) and interactive modes.
  - `GatewayKunRuntime` adapter provides `process_direct()` backed by KUN pipeline.
  - All tests pass: 447 total (103 original + 344 new).

### Fixed (2026-06-08)
- **Keep accepted files visible in referenced context**:
  - Fixed issue where accepted files were not visible in referenced context after acceptance

### Fixed (2026-05-25)
- **Strip `<think>` reasoning blocks from assistant messages** (`ChatConsole.tsx`):
  - Added `stripThinkBlocks()` helper that removes `</think>` blocks (case-insensitive, multi-line) before passing content to `MarkdownContent`/`ReactMarkdown`

### Fixed (2026-05-22)
- **Fixes and refactor for the "Merge Changes" button**:
  - Fixed silent snapshot failures (exceptions in `_write_snapshot_to` were swallowed)
  - Fixed merge incorrectly deleting newly created files (unlinking files that were created when the snapshot was empty)
  - Fixed files reappearing after switching sessions (`SessionManager.save` append-only mode prevented `_tool_hint` changes from being persisted)
  - Refactored sidebar file tracking: moved `_tool_hint` out of `conversation.jsonl` into a separate `tracked_files.json`; accept/revert now only remove JSON entries without rewriting conversation history
- **SkillHub CSP and file extension fixes**:
  - Fixed CSP in `index.html` blocking fetch requests to `https://skills.sixiangjia.de` — added to `connect-src`
  - Fixed `skills_create` and `skills_upload` in `bridge/server.py` writing `skill.yml` instead of `SKILL.md`, causing installed skills to be invisible to the `SkillsLoader`

### Added (2026-05-22)
- **SkillHub registry integration** (`apps/desktop/src/renderer/features/skills/SkillHubPage.tsx`):
  - New "SkillHub" tab in the Skills page, alongside the existing "本地技能" (Local Skills) tab
  - Browsing: loads the full skill index from `https://skills.sixiangjia.de/index.json` and displays skills in a card grid
  - Search: debounced (300ms) keyword search via `/api/search?q=<keyword>`
  - One-click install: fetches `SKILL.md` from the registry and writes it to the workspace skills directory via the existing `skills.upload` IPC channel
  - Installed status: already-installed skills show an "已安装" (Installed) badge; loading and error states have inline feedback
- **Conversation archiving**:
  - Added an archive button on the right side of each conversation in the sidebar (visible on hover); archived conversations are hidden from the list
  - Added an "Archived" tab in Settings to view, restore, and permanently delete archived conversations
  - Implemented via `.archived` marker files with zero runtime overhead

### Added (2026-05-20)
- **SetupWizard WSL2 Installation Guide Steps**:
  - Added `wsl2` step to wizard flow (environment → wsl2 → provider) to guide Windows users through WSL2 installation
  - Automatically detects WSL2 installation status: installed/version/distribution/running
  - One-click installation when not installed (UAC elevation) + manual installation instructions
  - Guides `wsl --install -d Ubuntu` when WSL is installed but no distribution exists
  - Prompts upgrade command for WSL1; automatically skips on non-Windows
  - Added IPC channels `wsl:check` / `wsl:install` and `WslCheckResult` type
- **Settings Page "Rerun Configuration Wizard" Button**:
  - Added "Reconfigure" section at the bottom of Settings → General tab, click to reopen SetupWizard
  - Controls AppShell `needsSetup` state via React props callback chain, no additional IPC channel required

### Added (2026-05-18)
- **Experience panel** (`apps/desktop/src/renderer/features/experience/`):
  - `ExperiencePage` component: Facts / Rules / History three tabs
  - `ExperienceStore` unified read interface, consolidating facts/rules/traces data
  - Experience IPC bridge handlers: `experience:list` / `delete` / `toggle` / `search`
- **MCPs management page** (`apps/desktop/src/renderer/features/mcps/`):
  - `MCPsPage` component: MCP service list with add/edit/delete actions
  - MCP list/upsert/delete IPC and bridge handlers
- **Skills CRUD**:
  - Desktop Skills page: create / upload / delete operations
  - `skill_manage` tool: agents can create, view, modify, and archive workspace skills
  - `skill_curator`: LLM-driven skill lifecycle management, automatically archives stale skills
- **Session management improvements**:
  - Session directory restructuring: each session stored in its own directory
  - Session-scoped working directory: file writes isolated to the current session directory
  - Automatically add `sessions/` to `.gitignore`
  - Session title support: sidebar shows custom titles
- **Trace task tracking system**:
  - Task Graph git-like self-improvement system (`miqi/agent/trace/`)
  - Full trace lifecycle: `trace_begin` → `record_step` → `trace_end`
  - CLI `miqi trace` command: `log` / `show` / `search` / `export` / `import`
  - Semantic search: vector similarity search based on `fastembed`
  - Context injection: automatically inject similar historical tasks into the system prompt
  - Nudge system: periodic reminders to agents to close open tasks
- **UI improvements**:
  - Settings page consolidation: providers / channels / approvals / cron merged into tabs
  - Sidebar improvements: session status filters, tracked file preview
  - Light theme color palette (WorkBench style)
  - Chat Console: session title, new chat button, context menu
  - Right-click context menus for chat / sessions / workspace / memory pages

### Added (2026-05-15)
- **Task Graph — git-like agent self-improvement system** (`miqi/agent/trace/`):
  - `TraceStore`: SQLite WAL-backed storage at `{workspace}/traces/TRACES.sqlite` with FTS5 full-text index and optional BLAKE3 content-addressed hashing (`miqi/agent/trace/store.py`).
  - `TaskTrace` / `TaskStep` data model with `trace_hash`, `goal`, `tool_calls`, `outcome`, `outcome_notes`, `embedding`, `parent_hash`, and `session_id` fields (`miqi/agent/trace/model.py`).
  - `Embedder`: lazy-loaded local embeddings via `fastembed` (`intfloat/multilingual-e5-small`, 384-dim, ONNX); cosine-similarity semantic search; graceful FTS5 fallback when `fastembed` is unavailable (`miqi/agent/trace/embedder.py`).
  - Three new agent tools: `task_begin` (open a trace), `task_end` (close with outcome + notes, returns similar historical traces), `trace_search` (semantic/FTS5 search of task history) (`miqi/agent/tools/task_trace.py`).
  - Context injection: up to 3 similar historical traces are prepended to `build_system_prompt()` when cosine similarity ≥ 0.65 (`miqi/agent/context.py`).
  - Nudge system: every `trace_nudge_interval` turns (default 8), a system message reminds the agent to call `task_end` if a task is open (`miqi/agent/loop.py`).
  - Auto-close: open tasks are closed as `partial` on `AgentLoop.stop()` (process shutdown) and on `/new` session reset (`miqi/agent/loop.py`).
  - Legacy lesson migration utility: converts `LESSONS.jsonl` entries to minimal `TaskTrace` records idempotently (`miqi/agent/trace/migrate.py`).
  - CLI sub-command `miqi trace` with `log`, `show`, `search`, `export`, `import` commands (`miqi/cli/trace_cmd.py`, `miqi/cli/commands.py`).
  - Six new config fields in `AgentSelfImprovementConfig`: `trace_enabled`, `embedding_model`, `trace_inject_top_k`, `trace_similarity_threshold`, `trace_nudge_interval`, `lessons_legacy_inject_enabled` (`miqi/config/schema.py`).
  - Optional dependency group `[trace]`: `fastembed>=0.6.0`, `numpy>=1.24.0`, `blake3>=0.4.0` (`pyproject.toml`).
- **`task_begin` / `task_end` / `trace_search` tool concurrency classification**: `trace_search` added to `_PARALLEL_SAFE_TOOLS`; `task_begin` and `task_end` added to `_PATH_SCOPED_TOOLS` (`miqi/agent/tools/registry.py`).
- **`execute_concurrent` `default_kwargs` forwarding**: added `default_kwargs` parameter to `ToolRegistry.execute_concurrent()` so `session_id` is correctly propagated to trace tools in the parallel dispatch path (`miqi/agent/tools/registry.py`).

### Fixed (2026-05-15)
- **`/new` session reset**: `session.clear()` was missing after successful archival and open-task auto-close; stale messages persisted into the new session (`miqi/agent/loop.py`, fix commit `347e9b5`).
- **Legacy lesson tests**: two tests in `test_tool_validation.py` assumed `record_tool_feedback()` / `record_user_feedback()` write lessons by default; they now explicitly opt in with `lessons_legacy_inject_enabled=True` to match the new Phase 5 kill-switch default (`tests/test_tool_validation.py`, fix commit `8b7e42a`).

### Changed (2026-05-15)
- **Legacy lesson injection disabled by default**: `MemoryStore` now defaults to `lessons_legacy_inject_enabled=False`; the `## Lessons` block is no longer included in `get_memory_context()` output unless explicitly opted in. Lesson write paths (`record_tool_feedback`, `record_user_feedback`) are gated by the same flag. Existing `LESSONS.jsonl` data is preserved on disk (`miqi/agent/memory/store.py`).

---

### Added (2026-05-14)
- **Memory tool** (`miqi/agent/tools/memory.py`): agent can now explicitly read/write/append long-term memory via the `memory` tool.
- **`session_search` tool** (`miqi/agent/tools/session_search.py`): FTS5-backed cross-session recall; lets the agent retrieve relevant past conversation snippets by natural language query.
- **`skill_manage` tool** (`miqi/agent/tools/skill_manage.py`): agent can create, view, patch, and archive workspace skills.
- **Nudge system**: periodic system-message reminders prompt the agent to persist memory and skills; interval configurable via `self_improvement.nudge_interval` (`miqi/agent/loop.py`).
- **System-prompt guidance** for memory, skills, and `session_search` tools injected into every turn (`miqi/agent/context.py`).
- **Skill curator** (`miqi/agent/memory/skill_curator.py`): LLM-driven lifecycle management — auto-archives stale skills after configurable threshold.
- **Lesson lifecycle management** (`miqi/agent/memory/lessons.py`): lessons now track `state` (`active` / `stale` / `archived`); auto-transition based on `lesson_stale_days` / `lesson_archive_days` config fields.
- **Lesson unlearn button and state badge** in MemoryPage desktop UI (`apps/desktop/src/renderer/features/memory/MemoryPage.tsx`).

### Added
- **Sidebar redesign**: Added session status filters to sidebar; introduced tracked file parsing and preview panel in chat console; refactored styling to use inline CSS variables over Tailwind arbitrary values; added debug logging for bridge stderr and runtime log flow (`apps/desktop/src/renderer/components/Sidebar.tsx`, `apps/desktop/src/renderer/features/chat/ChatConsole.tsx`).
- **Python backend hot reload**: Added automatic hot reload for Python backend code changes. When running in development mode, changes to `.py` files in the `miqi/` directory automatically trigger a bridge restart (`apps/desktop/src/main/bridge.ts`).
- **File diff and revert functionality**: Added file snapshot system that saves original content before first write, enabling non-git diff comparison and revert operations (`miqi/bridge/server.py`).
- **Merge all changes**: Implemented merge functionality for all file changes with file tracking (`miqi/bridge/server.py`).
- **Bundled bridge executable support**: Added support for packaging `miqi-bridge.exe` with Electron app, enabling standalone desktop deployment without requiring Python installation (`apps/desktop/src/main/bridge.ts`, `apps/desktop/electron-builder.yml`).
- **Global right-click context menu**: Added to chat, sessions, workspace, and memory pages (`apps/desktop/src/renderer/components/ContextMenu.tsx`, `apps/desktop/src/main/index.ts`).

### Changed
- Updated README: Rewrote for MiQi Desktop with English content and added Chinese translation (`README.md`, `README_zh.md`).
- Adjusted code formatting: Set printWidth to 80 and reformatted code (`apps/desktop/.prettierrc`).

### Fixed
- Fixed file operation tool hint truncation: Skip truncation for file operation tool hints to preserve full file paths (`miqi/agent/loop.py`).
- Fixed chat input alignment: Adjusted chat input alignment and line height for better visual appearance (`apps/desktop/src/renderer/features/chat/ChatInput.tsx`).
- Fixed IPC bridge startup: Ensured bridge is started before IPC calls and improved accessibility (`apps/desktop/src/renderer/contexts/RuntimeContext.tsx`).

### Documentation
- Added documentation for MiQi Desktop app features and development setup (`README.md`).



### Added
- Added **Agent 配置** step (step 4) to Setup Wizard: lets first-time users set Agent name, workspace directory (with Browse button), and optional Brave Search API key before finalising setup (`apps/desktop/src/renderer/features/setup/SetupWizard.tsx`).
- Added finish screen summary card showing configured provider, agent name, workspace, and web-search state before saving (`apps/desktop/src/renderer/features/setup/SetupWizard.tsx`).
- Expanded `CONFIG_WRITE_INITIAL` IPC handler to write `agents.defaults.name`, `agents.defaults.workspace`, and `tools.web.search.apiKey` in addition to provider key and model (`apps/desktop/src/main/ipc/index.ts`).
- Expanded `window.miqi.setup.writeInitialConfig` preload API to accept `agentName`, `workspace`, and `braveApiKey` optional parameters (`apps/desktop/src/preload/index.ts`).
- Replaced single-view Settings page with a tabbed layout: **通用** (agent name, workspace, model, temperature, max tokens), **Web 工具** (Brave Search API key), **外观** (light/dark/system theme toggle), and **运行日志** (existing logs viewer) (`apps/desktop/src/renderer/features/settings/SettingsPage.tsx`).

### Fixed
- Fixed Electron desktop session not persisting assistant replies: `_run_agent_loop` returns `final_content` separately from `messages`; `_save_turn` never saw it.  
  Now explicitly appends the final assistant message to `session.messages` before `sessions.save()` (`miqi/agent/loop.py`).
- Fixed Electron desktop chat messages lost when switching navigation tabs: `ChatConsole` was conditionally rendered and unmounted on every tab change.  
  Component is now always mounted; hidden/shown via CSS `hidden` class so React state is preserved (`apps/desktop/src/renderer/App.tsx`).
- Fixed Electron desktop chat showing no prior history on app restart or session change: `ChatConsole` now loads session history from `window.miqi.sessions.get()` on mount and on `sessionKey` prop changes, converting JSONL records to UI messages (`apps/desktop/src/renderer/features/chat/ChatConsole.tsx`).
- Fixed Electron desktop assistant responses appearing instantaneously with no visual feedback: added requestAnimationFrame-based typewriter animation that reveals reply text ~4 characters per frame; an animated cursor block is shown while the response is assembling (`apps/desktop/src/renderer/features/chat/ChatConsole.tsx`).

### Added
- Added **New Session** button to Chat Console toolbar: sends `/new` to the agent bridge and clears the local message list (`apps/desktop/src/renderer/features/chat/ChatConsole.tsx`).
- Added session key label to Chat Console toolbar so users can see which session is active (`apps/desktop/src/renderer/features/chat/ChatConsole.tsx`).
- M1 Electron desktop shell (`apps/desktop/`):
  - Python bridge (`miqi/bridge/server.py`) with stdin/stdout JSON-line protocol for chat streaming, session management, config CRUD, and provider operations.
  - Electron main process with secure BrowserWindow (contextIsolation + sandbox), BridgeManager for MiQi subprocess lifecycle, and 12 typed IPC handlers with zod validation.
  - Secure preload API via contextBridge exposing only typed RPC methods.
  - Setup wizard: 4-step flow (welcome → environment check → provider config with connection test → save & launch).
  - Chat console with streaming progress display, tool-call hints, code rendering, and copy support.
  - Session explorer: split-pane list and detail view with delete.
  - Settings: runtime logs viewer with auto-scroll, error highlighting, and export.
  - MiQi design system: warm neutral palette, Inter font bundled locally, Tailwind v4 + Radix primitives.

### Added
- **KUN runtime migration — Phase 0 (Analysis & Design)**:
  - Added comprehensive migration design document `docs/kun-runtime-migration.md`.
  - Document covers: architectural comparison (message-bus vs desktop workbench), 33-module KUN→Python mapping table, 15 capability adapter mappings, Pydantic data model definitions, 9-risk register, and an 11-phase migration plan with 11 recommended PR splits.
  - No code changes — read-only analysis phase.

- **KUN runtime migration — Phase 8 (AgentLoop Core)**:
  - Added `miqi/kun_runtime/loop.py` — KUN AgentLoop port: full `runTurn()` pipeline (drain steering → model_step → tool dispatch → compaction → loop), parallel-safe tool batching (max 3 concurrent reads), tool storm breaker integration, pipeline stage events, usage recording, interrupt/abort support.
  - Added `miqi/kun_runtime/compactor.py` — ContextCompactor with soft/hard/force thresholds, planCompaction + compact with summary generation.
  - Added `miqi/kun_runtime/context_estimator.py` — Token estimation (4 chars ≈ 1 token) for items and model requests.
  - Added `miqi/kun_runtime/history_repair.py` — healLoadedHistoryItems (normalization + repair) and repairModelHistoryItems (orphan tool result removal, stub injection).
  - Added `miqi/kun_runtime/history_hygiene.py` — applyRequestHistoryHygiene with line/byte/token budget trimming, signal-line preservation, single-line truncation.
  - Added `miqi/kun_runtime/token_economy.py` — normalizeTokenEconomyConfig, TOKEN_ECONOMY_INSTRUCTION constant.
  - Added `miqi/kun_runtime/tool_call_repair.py` — repairDispatchToolArguments with wrapper flattening, JSON string scavenging, oversized string truncation.
  - Added `miqi/kun_runtime/tool_storm_breaker.py` — ToolStormBreaker with windowed identical-call detection, exempt tools, reset.
  - Added `miqi/kun_runtime/auto_model_router.py` — resolveAutoModelRoute with candidate selection and fallback.

- **KUN runtime migration — Phase 9 (HTTP Runtime Composition)**:
  - Added `miqi/kun_runtime/auth.py` — BearerTokenAuth with insecure mode and token extraction.
  - Added `miqi/kun_runtime/runtime.py` — KunRuntime composition root (factory) wiring all Phase 1-8 components: EventBus, stores, services, compactor, gates, AgentLoop with lazy initialization.
  - Added `tests/kun_runtime/test_agent_loop_basic.py` with 12 tests: text completion, pipeline events, text deltas, item persistence, tool dispatch, multiple tool calls, error handling, interrupt/abort, model errors, compaction, tool storm suppression, usage accumulation.
  - Added `tests/kun_runtime/test_history_repair.py` with 26 tests: history healing (orphan removal, stub injection), history hygiene (oversized + single-line trimming), token economy, tool storm breaker (suppression, exempt, reset), tool call repair (wrapper flatten, JSON parsing, truncation), compactor (plan/compact/noop), context estimator, auto model router.
  - Added `tests/kun_runtime/test_http_runtime.py` with 11 tests: BearerTokenAuth, composition errors, full end-to-end turn lifecycle, multi-turn threads, thread listing, events sinceSeq replay.
  - All tests pass: 373 total (103 original + 270 new).

- **KUN runtime migration — Phase 7 (ApprovalGate & UserInputGate)**:
  - Added `miqi/kun_runtime/approval_gate.py` — `ApprovalGate` with async request/resolve/cancel_all, per-turn filtering, timeout→deny safety, idempotent resolve.
  - Added `miqi/kun_runtime/user_input_gate.py` — `UserInputGate` with async request/resolve/cancel_all, answers dict, timeout→cancelled fallback.
  - Added `tests/kun_runtime/test_agent_loop_gates.py` with 21 tests covering: ApprovalRequest lifecycle (resolve allow/deny, cancel, wait+timeout), ApprovalGate (parallel request+resolve, deny, cancel_all per-turn isolation), UserInputRequest lifecycle, UserInputGate (request+resolve with answers, cancel_all, nonexistent rejection).
  - All tests pass: 324 total (103 original + 221 new).

- **KUN runtime migration — Phase 6 (ToolHost adapter)**:
  - Added `miqi/kun_runtime/tool_host.py` — KUN ToolHost wrapping MiQi ToolRegistry:
    - `MiQiToolHost`: delegates `listTools(context)` and `execute(call, context)` to the registry with KUN-compatible ToolHostResult items.
    - Tool kind classification: `bash/exec` → command_execution, `write/edit/delete` → file_change, others → tool_call.
    - Concurrency: delegates to `ToolRegistry.should_parallelize()` with path-scoped parallel-safe rules; untrusted/never approval policies force sequential.
    - `FakeToolHost`: test double with configurable tool list, results, error tools, and call recording.
    - `ToolHostContext` dataclass with thread/turn/workspace/model info, approval/user-input callbacks, abort signal, and skill/memory/delegation policies.
  - Added `tests/kun_runtime/test_tool_host.py` with 24 tests covering: tool kind classification, list_tools (full listing + allowed-name filtering), execute (normal, read_file, error handling, unknown tool, result shape), concurrency (parallel-safe, same-path serialization, different-path parallelization, mixed, untrusted policy), and FakeToolHost (configured tools/results/errors, call recording, parallel classification).
  - All tests pass: 303 total (103 original + 200 new).

- **KUN runtime migration — Phase 5 (ModelClient adapter)**:
  - Added `miqi/kun_runtime/model_client.py` — KUN-compatible model client:
    - `MiQiModelClient` wraps `LLMProvider.chat()` with pseudo-streaming (Phase 5a): converts `ModelRequest` to provider messages, yields `assistant_reasoning_delta`, `assistant_text_delta`, `tool_call_complete`, `usage`, and `completed` chunks.
    - `FakeModelClient` test double with configurable text/reasoning/tool/usage/error responses and request recording.
    - `ModelRequest`, `ModelToolSpec`, `ModelStreamChunk` dataclasses matching KUN wire format.
    - TurnItem → OpenAI message conversion for all 10 item kinds.
    - Tool spec → OpenAI function definition conversion.
  - Added `tests/kun_runtime/test_model_client.py` with 27 tests covering: FakeModelClient text/tools/reasoning/usage/error/recording, 6 item→message conversions, 4 build_messages scenarios, tool spec conversion, and 7 MiQiModelClient integration tests (text, reasoning, tools, usage, provider error, API error, tool passing).

- **Security fix — Phase 3 stores**: Added `os.chmod(0o600)` to all file writes in `FileThreadStore.upsert()`, `FileSessionStore.append_item()`, `FileSessionStore.append_event()`, and `FileSessionStore._rewrite_items_file()` to restrict session/thread files to owner-only (matching MiQi's existing security practice in `config/loader.py` and `session/manager.py`).

- **KUN runtime migration — Phase 4 (TurnService, ThreadService, Cancellation, MigrationAdapter)**:
  - Added `miqi/kun_runtime/cancellation.py` — `CancellationToken` (asyncio.Event-based cooperative cancellation) and `InflightTracker` (running operation accounting per thread/turn).
  - Added `miqi/kun_runtime/thread_service.py` — `ThreadService` with create/get/list/update/delete/fork, event recording for thread_created/thread_updated.
  - Added `miqi/kun_runtime/turn_service.py` — `TurnService` with full lifecycle: start_turn (creates turn + user item, abort token, inflight tracking), finish_turn (completed/failed/aborted with item finalization), interrupt_turn (abort token + optional discard), steer_turn (drain steering), apply_item, update_item, get_turn.
  - Added `miqi/kun_runtime/migration_adapter.py` — deterministic `session_key → threadId` bidirectional mapping with register/clear support.
  - Added `tests/kun_runtime/test_turn_service.py` with 38 tests covering: CancellationToken lifecycle, InflightTracker accounting, session→thread mapping determinism, ThreadService CRUD/fork/events, TurnService start/finish/interrupt/steer/items/cancellation lifecycle.
  - All tests pass: 252 total (103 original + 149 new).

- **KUN runtime migration — Phase 3 (ThreadStore, SessionStore, UsageService)**:
  - Added `miqi/kun_runtime/stores.py` — file-based persistent stores:
    - `FileThreadStore`: one JSON file per thread (upsert/get/delete/list), atomic write via os.replace.
    - `FileSessionStore`: append-only JSONL for TurnItems and runtime events (load_items, append_item, update_item, rewrite_items, append_event, load_events_since).
    - All paths relative to configurable `data_dir` — tests use `tmp_path` for isolation.
  - Added `miqi/kun_runtime/usage.py` — `UsageService` for per-thread token/cost accumulation with token economy savings tracking, seed/reset, and thread isolation.
  - Added `tests/kun_runtime/test_stores.py` with 26 tests covering: thread CRUD, persistence across instances, session item append/load/update/rewrite ordering, event sinceSeq filtering, corrupt line handling, thread isolation, and usage accumulation/savings/seed/reset.
  - All tests pass: 214 total (103 original + 111 new).

- **KUN runtime migration — Phase 2 (EventBus, SSE, RuntimeEventRecorder)**:
  - Added `miqi/kun_runtime/event_bus.py` — in-memory per-thread event bus with monotonically increasing seq, append, history replay, sinceSeq filtering, and async subscribe (AsyncIterator).
  - Added `miqi/kun_runtime/event_recorder.py` — RuntimeEventRecorder that auto-assigns seq + timestamp and records to the event bus.
  - Added `miqi/kun_runtime/sse.py` — SSE encoder producing KUN-compatible format (`id: <seq>\nevent: <kind>\ndata: <json>\n\n`), plus comment and [DONE] markers.
  - Added `tests/kun_runtime/test_event_bus.py` with 27 tests covering: seq monotonicity, per-thread isolation, append ordering, history/sinceSeq filtering, async subscribe with replay + live events, recorder seq/timestamp auto-assignment, SSE field format, JSON round-trip, and special characters.

- **KUN runtime migration — Phase 1 (Contracts & Event Model)**:
  - Added `miqi/kun_runtime/` package with `contracts.py` — Pydantic v2 models for the complete KUN data model:
    - 10 `TurnItem` variants (user_message, assistant_text, assistant_reasoning, tool_call, tool_result, approval, user_input, compaction, review, error) as discriminated union.
    - 32 `RuntimeEvent` variants (thread/turn lifecycle, item lifecycle, streaming deltas, tool events, approval/user-input gates, compaction, goal/todo, pipeline stage, usage, error, heartbeat) as discriminated union.
    - Thread/Turn models: `ThreadRecord`, `ThreadSummary`, `Turn`, `ThreadGoal`, `ThreadTodoList`.
    - Request/Response models: `StartTurnRequest/Response`, `SteerTurnRequest`, `InterruptTurnRequest/Response`, `CompactRequest/Response`, `CreateThreadRequest`, `ForkThreadRequest`, `UpdateThreadRequest`, `SetThreadGoalRequest`, `ApprovalDecisionRequest`, `UserInputResolveRequest`.
    - Supporting types: `UsageSnapshot`, `ModelToolSpec`, `ModelCapabilityMetadata`, 11 enums, `PipelineStage` literal with labels.
    - All models use camelCase field names matching KUN HTTP/SSE payloads for wire compatibility.
  - Added `tests/kun_runtime/test_contracts.py` with 58 tests covering: serialization round-trips, enum validation, discriminator dispatch, default values, field constraints (min_length, ge), empty/id rejection, and `ThreadTodoList` at-most-one-in-progress invariant.

### Documentation
- Added uv installation instructions to README, getting-started, developer-guide, and contributing docs; uv is the recommended install method, pip retained as fallback.
- Updated `maxTokens` default from `16000` to `8192` in `docs/configuration.md` to match code.
- Added GitHub Copilot (OAuth) to README LLM Providers feature list.
- Fixed `ff agent` → `miqi agent` in historical changelog entries.
- Updated README and project docs to match current code paths and schema defaults:
  - corrected workspace-relative memory/session storage paths (`<workspace>/memory`, `<workspace>/sessions`)
  - documented current packaged gateway scope (Feishu wired today; other channel adapters remain extension modules)
  - refreshed config defaults for memory, sessions, self-improvement, heartbeat, cron, and shell execution
  - documented MCP `lazy`, `description`, `headers`, and environment-inheritance behavior
  - clarified that SQLite session storage, provider fallback chains, command approval, and smart routing exist as shipped modules/helpers but are not all enabled by default in the packaged CLI/gateway path

### Added
- Added `paper-research` skill (`miqi/skills/paper-research/SKILL.md`):
  - Full workflow: `paper_search` → `paper_download` → `translate_pdf` → summarize with references.
  - Covers scheduled briefing scenarios (cron + feishu delivery).
  - Includes `web_search` fallback for news and preprints not indexed in Semantic Scholar.
- Added `feishu-report` skill (`miqi/skills/feishu-report/SKILL.md`):
  - Format decision table: plain text / card message / Feishu Doc / calendar event / task.
  - Covers `send_message`, `send_card_message`, `create_document` + `write_document_markdown`, `create_calendar_event`, `create_task`.
  - Includes user identity resolution via `resolve_users_by_name` and `get_chat_members`.
- Added `workspace-cleanup` skill (`miqi/skills/workspace-cleanup/SKILL.md`):
  - Organizes `~/.miqi/workspace` into structured `artifacts/` subdirectories.
  - Archives files older than 30 days to `archive/YYYY-MM/`.
  - Defines sacred directories (memory/, skills/, sessions/, system .md files) that are never touched.

### Changed
- Updated `cron` skill (`miqi/skills/cron/SKILL.md`):
  - Corrected timezone fallback documentation: without `tz`, cron expressions are now evaluated in **UTC** (not server local time).
  - Updated `at` mode examples to always include timezone offset (e.g. `+08:00`) or explicit `tz=`.
  - Added China Standard Time (`Asia/Shanghai`) examples to time expression table.
- Updated `cron` tool parameter descriptions (`miqi/agent/tools/cron.py`):
  - `message`: clarified it is the full task prompt executed at trigger time, not just a label.
  - `cron_expr`: added explicit warning that expressions default to UTC; must pass `tz=` for non-UTC users.
  - `at`: updated example to include timezone offset; documents `tz=` fallback for naive datetimes.
  - `tz`: extended to apply to both `cron_expr` and `at` modes.

### Fixed
- Fixed `max_tokens` default of 16000 exceeding DeepSeek API maximum (8192 output tokens): lowered `AgentDefaults.max_tokens` back to 8192. After migration from litellm (which auto-capped per model) to direct SDK calls (which do not), the previous 16000 default caused 400 BadRequest errors on DeepSeek (`config/schema.py`).
- Fixed `_match_provider()` using bare `api_key` truthiness check, preventing `is_local` providers (vLLM, Ollama Local) from matching when they use `api_base` instead of `api_key`: replaced with `_is_configured()` helper that checks both `api_key` and `api_base` (`config/schema.py`).
- Fixed `build_provider()` not passing `provider_name` and `default_model` to fallback-chain provider constructors, causing fallback providers to use wrong endpoints and model names (`config/schema.py`).
- Fixed `_make_provider()` in onboard CLI requiring `api_key` for `is_local` providers (vLLM, Ollama Local) that only need `api_base`: added `is_local` exemption to the api_key requirement check (`cli/commands.py`).
- Fixed `AnthropicProvider` passing empty-string `api_key` to SDK instead of `None`, preventing the SDK from falling back to `ANTHROPIC_API_KEY` environment variable (`providers/anthropic_provider.py`).
- Fixed cron `at` mode silently using server local timezone for naive datetime strings: naive datetimes now interpreted as UTC when no `tz` is provided; `tz=` can be passed together with `at=` to override (`miqi/agent/tools/cron.py`).
- Fixed `tz` parameter rejected when combined with `at`: removed erroneous validation that blocked `tz` + `at` combinations (`miqi/agent/tools/cron.py`).
- Fixed cron `cron` mode using unpredictable server local timezone as fallback: now falls back to UTC for deterministic behavior across deployment environments (`miqi/cron/service.py`).
- Fixed `miqi agent` mode (CLI) silently ignoring all cron jobs: `on_job` callback was never registered and `cron.start()` was never called; both now wired correctly in `cli/agent_cmd.py`.
- Fixed `miqi agent` mode not propagating `job_timeout` from config to `CronService` (`miqi/cli/agent_cmd.py`).

### Removed
- Removed `clawhub` skill (`miqi/skills/clawhub/`) — not applicable to this deployment.

---

## [Unreleased — previous]

### Added
- Added Feishu group chat @mention filtering (`channels/feishu.py`):
  - New config `channels.feishu.requireMentionInGroups` (default `true`).
  - In group chats, messages are only forwarded to the agent when the bot is @mentioned.
  - @mention placeholder (`@_user_N`) is automatically stripped from the message text.
  - Private chats (p2p) remain unaffected and always forwarded.
- Added MCP tool heartbeat progress reporting (`agent/tools/mcp.py`, `agent/loop.py`):
  - New config `tools.mcpServers.<name>.progressIntervalSeconds` (default `15`).
  - During long-running MCP tool calls, periodic status messages are sent to the user (e.g. "⏳ raspa_run_simulation 正在执行中... (已用时 1m30s)").
  - Heartbeat task is automatically cancelled when the tool finishes.
  - Existing MCP SDK progress callbacks remain functional alongside heartbeat.
- Added task queue tracker with user notifications (`agent/loop.py`):
  - New `TaskTracker` class tracks active and pending tasks.
  - New config `channels.sendQueueNotifications` (default `true`).
  - When agent is busy, new messages are queued and senders receive position notifications (e.g. "✅ 收到！当前正在处理 Alice 的任务，您排在第 2 位，请稍候。").
  - When a queued task starts processing, sender receives "🚀 开始处理您的任务...".
  - CLI and system messages bypass the queue for immediate processing.
- Added `sender_name` field to `InboundMessage` (`bus/events.py`) for display-friendly queue notifications.
- Added `sender_name` parameter to `BaseChannel._handle_message()` (`channels/base.py`).
- Added tests for new features:
  - `tests/test_task_tracker.py`: TaskTracker unit tests, MCP heartbeat integration test, InboundMessage sender_name tests.
  - `tests/test_feishu_mention_filter.py`: Feishu group @mention filtering tests, config schema tests.
- Added modular CLI command files:
  - `miqi/cli/onboard.py`
  - `miqi/cli/agent_cmd.py`
  - `miqi/cli/gateway_cmd.py`
  - `miqi/cli/management.py`
- Added core regression tests:
  - `tests/test_agent_loop_core.py`
  - `tests/test_cron_service_core.py`
- Added project documentation:
  - `docs/API.md`
  - `docs/DEVELOPER_GUIDE.md`
  - `docs/ARCHITECTURE.md`
  - `CONTRIBUTING.md`
- Added Feishu business tools in `miqi/agent/tools/feishu.py`:
  - `feishu_doc` for cloud doc creation and optional plain-text write.
  - `feishu_calendar` for calendar event creation and attendee assignment.
  - `feishu_task` for task creation with group-member assignment.
  - `feishu_drive` for Drive folder creation (`create_folder` / `ensure_folder_path`) and workspace file uploads.
  - `feishu_handoff` as a generic collaboration handoff layer that orchestrates delivery steps.
- Added Feishu mention metadata extraction (`sender_open_id`, `mentions`) in `miqi/channels/feishu.py`.
- Added Feishu tool usage guidance in `miqi/templates/TOOLS.md`.
- Added `paper_download` tool in `miqi/agent/tools/papers.py` to download PDFs into workspace.
- Added documentation updates for Feishu collaboration + paper delivery workflow:
  - README feature/capability updates
  - API docs for `paper_download`, `feishu_drive`, and `feishu_handoff`
  - Feishu backend permission checklist in `docs/API.md`

### Changed
- Refactored `miqi/cli/commands.py` into an entry/compatibility layer that registers split command modules.
- Refactored arXiv XML parsing in `miqi/agent/tools/papers.py` by extracting shared `_parse_arxiv_entry` logic.
- Replaced remaining built-in `print()` calls with `loguru.logger` warnings in `miqi/config/loader.py`.
- Split memory implementation into package modules with `MemoryStore` facade in `miqi/agent/memory/store.py`.
- Normalized provider `api_base` handling in `LiteLLMProvider` to auto-fill missing default base paths (for example `/v1`, `/api/v1`) when users provide host-only URLs, while preserving explicit custom paths.
- Updated `AgentLoop` tool wiring in `miqi/agent/loop.py` to:
  - auto-register Feishu business tools when Feishu credentials are configured.
  - propagate message context (`channel`, `chat_id`, `message_id`, `sender_id`, `metadata`) into Feishu tools for group assignment resolution.
  - include the generic Feishu handoff tool in runtime registration/context propagation.
- Added paywall-aware PDF download behavior:
  - detects common login/paywall HTML responses and returns structured errors instead of saving invalid `.pdf` files.
- Updated Feishu Drive upload implementation to support multipart upload (分片上传) for files > 20 MB:
  - `_upload_file_multipart()`: full 3-step flow — `upload_prepare` → `upload_part × block_num` → `upload_finish`.
  - Auto-routing in `_upload_file()`: ≤ 20 MB → `upload_all`, > 20 MB → multipart.
  - Added `_FEISHU_UPLOAD_ALL_MAX_BYTES = 20 MB` constant (per Feishu official docs 2024-10-23 hard limit).
- Added `feishu_drive` action `grant_permission`: calls `POST /open-apis/drive/v1/permissions/:token/members` to grant doc/file access to a user or group chat.
- Added `_grant_permission()` helper to `FeishuToolBase` (shared across doc/drive tools).
- Added `grant_chat_access` parameter to `feishu_doc`: when `true`, auto-grants current group chat view access after doc creation.
- Added `docs/API.md` corrections based on Feishu Open Platform official docs (2026-02-26 verification):
  - `Permission Management` vs `Events & Callback` setup guide reorganized.
  - Two-layer permission model explanation (scopes ≠ resource access).
  - Drive: full multipart upload flow documented; Adler-32 checksum requirement noted.
  - Drive: `permission-member/create` API fully documented including group-chat limitations.
  - Calendar: corrected HTTP method from GET to POST for `calendar.v4.calendar.primary`.
  - Task: corrected API version — v2 is the latest (`POST /open-apis/task/v2/tasks`, updated 2025-06-04).
  - Updated "Current Implementation Limits" to reflect new capabilities.

### Fixed
- Fixed Feishu Drive upload checksum algorithm: replaced MD5 (`_md5_file`) with Adler-32 (`_adler32_file` via `zlib.adler32`). The Feishu `upload_all` API requires Adler-32 decimal string; MD5 caused API error `1062008`.
- Fixed Moonshot/Kimi requests failing with 404 (`/chat/completions`) when `apiBase` was configured without `/v1`.
- Fixed heartbeat false trigger: empty `HEARTBEAT.md` no longer fires a heartbeat notification (`heartbeat/service.py`).
- Fixed reflection prompt (`_REFLECT_PROMPT`) being visible to users — demoted from `role: "user"` to `role: "system"` so it is excluded from session history and never sent to the user (`agent/loop.py`).
- Fixed long-task max-iteration message: Chinese-language "processing limit" notification now correctly delivered to users (`agent/loop.py`).
- Fixed progress messages suppressed under default config: milestone and MCP heartbeat notifications now set `_tool_hint=False` so they pass through when `send_progress=True` (default) (`agent/loop.py`).
- Fixed queue position notification: elapsed time now computed from `start_time` (when task started processing) instead of `enqueue_time` (when task arrived) (`agent/loop.py`).
- Fixed `record_tool_feedback` never called: tool execution results now feed into `LessonStore` for self-improvement learning (`agent/loop.py`).
- Fixed stale HISTORY.md references: removed from `context.py`, `AGENTS.md`, `skills/memory/SKILL.md`, `commands.py` — aligned with RAM-first memory architecture.
- Fixed LLM API errors silently passed as normal replies: `finish_reason == "error"` now returns a user-friendly error message instead of raw error content (`agent/loop.py`).
- Fixed `_save_turn` filter for reflect prompt: updated to match new `role: "system"` and made tool result truncation configurable via `session_tool_result_max_chars` (`agent/loop.py`, `config/schema.py`).
- Fixed `cron.status()` called before `cron.start()` in gateway startup: moved into `async run()` after service initialization (`cli/gateway_cmd.py`).
- Fixed subagent missing paper tools: `PaperSearchTool`, `PaperGetTool`, `PaperDownloadTool` now registered in subagent with `paper_config` propagated from main agent (`agent/subagent.py`).
- Fixed cron `every`-type schedule losing continuity on restart: `_compute_next_run` now uses `last_run_at_ms + interval` when available, with `is not None` guard for zero values (`cron/service.py`).
- Fixed subagent defaults misaligned with main agent: `temperature` 0.7→0.1, `max_tokens` 4096→8192 (`agent/subagent.py`, `agent/loop.py`).
- Fixed `MessageBus` queues unbounded: added `maxsize=1000` default to prevent memory leak under load (`bus/queue.py`).
- Fixed skills frontmatter YAML boolean parsing: now returns Python `True`/`False` instead of truthy strings, preventing `always: false` skills from being force-loaded (`agent/skills.py`).
- Fixed queue notification metadata using `_progress` key: changed to distinct `_queue_notification` key with corresponding dispatch filter in `ChannelManager`, preventing double-filtering by `send_progress` config (`agent/loop.py`, `channels/manager.py`).
- Fixed `save_config()` writing config file with default permissions (644): now calls `chmod 0o600` after write to protect API keys from other OS users (`config/loader.py`).
- Fixed `AgentLoop.stop()` leaving consolidation tasks orphaned on shutdown: `stop()` now cancels all in-flight `_consolidation_tasks` before clearing the running flag (`agent/loop.py`).
- Fixed tool execution having no timeout: `ToolRegistry.execute()` now wraps each tool call with `asyncio.wait_for(timeout=120s)` to prevent one hung tool from blocking all agent processing (`agent/tools/registry.py`).
- Fixed MCP reconnect retrying on every message with no delay: `_connect_mcp()` now uses exponential backoff (2 s → 4 s → … → 60 s cap) via `_mcp_retry_after` / `_mcp_backoff_secs` fields (`agent/loop.py`).
- Fixed LiteLLM retry loop using linear backoff (`0.5 * attempt`): replaced with exponential backoff and random jitter (`2^(attempt-1) * 0.5–1.0 s`, capped at 30 s) (`providers/litellm_provider.py`).
- Fixed `json_repair.loads()` silently fixing malformed LLM tool arguments with no visibility: now logs a `WARNING` message including the tool name and the original malformed JSON when repair is triggered (`providers/litellm_provider.py`).
- Fixed cron `_execute_job()` having no execution timeout: now wrapped with `asyncio.wait_for(timeout=600s)` to prevent a stuck job from blocking the entire cron scheduler (`cron/service.py`).
- Fixed `MessageBus.publish_inbound()` blocking forever when inbound queue is full: replaced `await put()` with drop-oldest strategy (logs warning, evicts oldest message); `publish_outbound()` now uses a 10 s `wait_for` timeout and logs an error if outbound consumers stall (`bus/queue.py`).
- Fixed channel send failures silently dropping messages: `_dispatch_outbound()` now retries up to 3 times with linear backoff (0.5 s, 1.0 s) before logging an error and discarding (`channels/manager.py`).
- Fixed `ToolRegistry` 120 s outer timeout overriding per-MCP `toolTimeout`: `Tool` base class gains `execution_timeout` property (default `None`); `MCPToolWrapper` overrides it to `toolTimeout + 5 s`; `ToolRegistry.execute()` prefers per-tool timeout when set (`agent/tools/base.py`, `agent/tools/mcp.py`, `agent/tools/registry.py`).
- Fixed unbounded parallel session consolidations: `AgentLoop` now holds `asyncio.Semaphore(5)` used by every consolidation task to cap concurrency and prevent memory spikes (`agent/loop.py`).
- Fixed critically underestimated MCP tool timeouts in `configure_mcps.sh`: raspa2 60 s → 21 600 s (6 h), zeopp 300 s → 600 s, mofstructure/miqrophi 120 s → 600 s — RASPA GCMC/MD simulations routinely run 4-5+ hours (`scripts/configure_mcps.sh`).
- Fixed pdf2zh MCP timeout severely underestimated at 800 s: default raised to 3 600 s (1 h) in both `miqi config pdf2zh` and `configure_mcps.sh` — translating a 50+ page paper can easily exceed 30 min depending on LLM response time (`cli/config_cmd.py`, `scripts/configure_mcps.sh`).
- Fixed `max_tool_iterations` default of 40 stopping complex scientific workflows mid-task: raised to 100. A RASPA GCMC + result parsing workflow can easily consume 30-50+ steps; 40 caused "⚠️ 已达到最大执行步数" errors. Configurable via `agents.defaults.maxToolIterations` in `config.json` (`config/schema.py`).
- Fixed `max_tokens` default of 8192 being too small for DeepSeek-R1 and extended Claude 4 responses: raised to 16 000 in `AgentDefaults`. LiteLLM itself has no cap; the 8192 ceiling was miqi's own config default (`config/schema.py`).
- Fixed DeepSeek-R1 (deepseek-reasoner) multi-turn conversations breaking when used via the official DeepSeek API: `_sanitize_messages` now preserves `reasoning_content` in assistant message history when the provider spec sets `supports_reasoning_history=True`; DeepSeek spec updated accordingly. OpenRouter/gateway paths are unaffected — reasoning is still stripped there (`providers/registry.py`, `providers/litellm_provider.py`).
- Fixed agent returning a silent empty response when a reasoning model (e.g. DeepSeek-R1 via OpenRouter) exhausts `max_tokens` during thinking and emits no visible answer text: `_strip_think` returning `None` now logs a warning and surfaces "⚠️ 模型完成了推理但未输出最终回复（可能是 max_tokens 设置过低）" to the user instead of sending nothing (`agent/loop.py`).
- Fixed cron `_execute_job()` hardcoded 600 s timeout killing long-running scientific jobs: `CronService` now accepts `job_timeout` parameter (default 86 400 s / 24 h) read from `config.cron.job_timeout_seconds`; gateway plumbs the value from config (`cron/service.py`, `config/schema.py`, `cli/gateway_cmd.py`).

### Tests
- Added provider routing regression tests for API base normalization behavior in `tests/test_provider_routing.py`.
