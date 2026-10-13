# Chat handoff / project context

> **Current branch policy (2026-10-13):** `master` is now the sole
> development branch for both Desktop and Android. The earlier `android-live`
> notes below are historical; new changes and rolling Android builds come
> from `master`. Desktop and Android both use `src/core.py`,
> `src/scoring.py` and `src/strategies.py` for decisions.
>
> The score table's `Σ` is an aggregate **stat percentage**, not points.
> A legal full-item swap's marginal score is decomposed into PvE, defense,
> Triple, Mega, normal and flexibility using one shared score-delta helper.


This file exists so a fresh ChatGPT chat can resume the work without reconstructing the history.

## Working agreement

- Personal project. Prefer simple, clean architecture over process overhead.
- Desktop/general work normally goes directly to `master`.
- Android is intentionally being developed on the live branch `android-live`.
- Keep **shared game/domain logic in Python**. Platform differences belong behind adapters.
- Keep desktop working: PC = ADB + PaddleOCR; Android = native screenshot/OCR/touch adapters + the same Python domain.
- Prefer fail-closed behavior for automation/OCR: if uncertain, CHECK/do nothing rather than guess and tap.
- Code style: clean architecture/SRP, intent-revealing names, short cohesive classes/methods.
- Do not sit polling GitHub Actions. After pushing, check CI at most once; if still running, report `CI pending` and return. There is no webhook/callback available here and repeated polling has caused several stalled turns.

## Repository / branch state

Repository: `yurii-zadryhun/dungeon-rush-loot`

Android branch: `android-live`

Last verified `android-live-latest` **release target** as checked 2026-10-12: `b2c887e3a5169c108e4e0204d04a9a56d360915b`. Python CI run `38176513154` and Android APK run `38176513137` passed for this production Universal version. Subsequent changes to simulation/benchmark/docs are on `android-live`; do not claim the newest release incorporates later files without verifying its target SHA. At handoff, offline benchmark run `38207762735` and CI run `38208007734` are confirmed successful; its code is analysis tooling, **not** an active new Auto policy.

## CURRENT PRIORITY — why Universal misses complementary gear; plan for next chat (2026-10-12)

**User's explicit handoff instruction (2026-10-12):** analyze the root cause and design what must change so the loot strategy behaves correctly; **DOCUMENT ONLY** in this chat. Do **not** implement policy, scoring or simulator changes until the next chat. The user is specifically interested in synergies between several items: an individually worse candidate may be essential to a stronger future combination. Do not switch focus to OCR, Android UX or generic code cleanup.

### Verified evidence / reproducibility (not speculation)

- Repo: \`yurii-zadryhun/dungeon-rush-loot\`, branch \`android-live\`. The main scoring implementation is shared Python; desktop uses PaddleOCR, Android uses ML Kit; both use \`src/scoring.py\` and \`src/strategies.py\`. Keep PVE/PVP untouched and Wings/Cape fixed unless deliberately expanding scope.
- Identical **deterministic** synthetic sample: \`random.Random(20261011)\`, \`tools.simulate_strategy_loot.random_item\`, **50,000** items, six interchangeable slots, start state \`tests/fixtures/strategy_start_equipment.json\`; \`Immortal/Divine [EXP]\` rarity 50/50, uniform level 1–130, three distinct normal and one or two distinct exceptional affixes, independent uniform roll values in configured caps. The stream and item indexes are reproducible **only with the same generator, config, Python RNG and seed**. This is a scoring/decision stress test, NOT real game drop probabilities. Crucially: the real game's next level may depend on the equipped level of that slot, so **holding the same sequence fixed across policies may be physically counterfactual**; verify actual mechanics when building a realistic simulator.
- Current production Universal (\`src/strategies.py::UniversalScoringStrategy\`) is PVE-first, with saturated special rewards for 2 CDT, 1 ranged defense, 1 melee defense, Triple, Mega, and item-specific priority for AS+Crit Damage+Crit Chance. The selected calibration was intentionally restored after several unsuccessful weight-tuning experiments. \`docs/universal-target-calibration.md\` records them. Current 50k greedy result: **41 EQUIP / 49,959 SELL**, final Universal \`2837.077\` and PVE \`1353.564\`.
- **Completed independent offline verification:** \`tools/offline_universal_benchmark.py\`, \`tests/test_offline_universal_benchmark.py\`, and \`docs/offline-universal-50k-feasibility.md\`. GitHub Actions run [38207762735](https://github.com/yurii-zadryhun/dungeon-rush-loot/actions/runs/38207762735) **success**, artifact [offline-universal-50k JSON/MD](https://github.com/yurii-zadryhun/dungeon-rush-loot/actions/runs/38207762735/artifacts/11727594427). SciPy/HiGHS MILP filtered **1,674** of the 50k drops into near-target candidates (2 exceptional target rolls, each CDT >=50 and each side-defense >=90 when present). It selected one item per slot under explicit coverage constraints, then evaluated the result using the **real nonlinear production** \`BuildScorer(Universal)\`, not the MILP's linear proxy.
- **Confirmed better attainable six-piece build:** Universal \`2883.623\` (**+46.546** vs greedy) and PVE \`1349.641\` (vs greedy \`1353.564\`, **−3.923**, ~0.29%). Selected zero-based drop indexes: Weapon **46035**, Helmet **43276**, Backpack **7730**, Gloves **9966**, Necklace **20910**, Ring **7686**. Both builds include unchanged Wings/Cape. Details are in \`docs/offline-universal-50k-feasibility.md\`.
- Selected alternative characteristics: two CDT **−64.56% / −63.84%**, Ranged Defense **99.52%**, Melee Defense **93.33%**, Triple **103.26% raw** (effective max 100%), Mega **37.19%**; AS on 5 standard items, CD on 3, CC on 2. Greedy was CDT −46.94/−52.99, RD 94.99, MD 97.28, Triple 104.74 raw, Mega 35.47; AS/CD/CC on 4/3/2 pieces. Alternative is better by the existing Universal objective and in several user target dimensions, but is **not a Pareto improvement in every dimension** (MD and PVE marginally worse).
- **Multi-item synergy is directly measured on the greedy final loadout:** substituting only Weapon \`−200.921\`, only Backpack \`−119.664\`, only Gloves \`−254.009\`, only Ring \`−143.892\` Universal points; two coordinated substitutions: Weapon+Backpack \`+5.870\`, Gloves+Ring \`+34.774\`; all four \`+46.546\`. These are counterfactual comparisons **against the final greedy state**, not an assertion that those exact score deltas occurred when those drops arrived. The candidate items from earlier drops cannot be recovered after SELL; e.g. alternate Backpack #7730 and Gloves #9966 were discarded before later final greedy replacements. This is a concrete **local optimum / complementarity** witness.
- **Exact target feasibility for THIS stream and specified role allocation:** six standard \`[EXP]\` pieces × at most two exceptional rolls = **12 exceptional slots**. Four defense slots are reserved (2 distinct CDT >=50, 1 RD >=90, 1 MD >=90). With remaining eight slots the only plausible Triple/Mega allocations meeting the caps (Triple 30 per roll, Mega 10 per roll) are **4 Triple + 4 Mega** or **3 Triple + 5 Mega**. MILP **proved infeasible** to simultaneously attain **Triple >=90 AND Mega >=40** under these role and quality constraints for these 50k drops. With 4 Mega and Triple >=90, the **exact maximum Mega is 39.79%**; with 3 Triple and Mega >=40, the **exact maximum Triple is 89.89%**. These are certificates for the stated *linear role/roll constraints and candidate pool*, **not** an exhaustive proof of a maximum nonlinear-score build nor real-game odds. Do not claim the user's precise ideal build is present in this pool.

### Root causes — distinct and cumulative

1. **Greedy one-step choice, not combinatorial planning.** \`ItemComparer._build_comparison()\` computes \`score(current, protected_slot=slot)\` versus \`score(current.with_replacement(slot, candidate), protected_slot=slot)\`, and EQUIPs iff \`delta > 0.01\`; otherwise SELL. This evaluates one replacement in the *current* loadout only. Nonadditive effects (CDT caps, per-role requirements, Triple/Mega tradeoffs, PVE combat interactions, normal AS+CD pairing, item primary scaling) produce valleys: useful jointly, harmful individually. A globally better final outfit may require temporarily declining current score.
2. **No actual lookahead despite the name.** \`BuildScorer._flexibility()\` removes affixes from the easiest other slots, computes current marginal losses, and adds a small static replacement-flexibility adjustment. It **does not** evaluate candidate drops, forecast future arrivals, reserve roles, optimize item assignments, or account for the cost of discarding an irreplaceable roll. Reweighting this proxy cannot guarantee anticipation of a future complementary drop.
3. **Different decision and reporting objectives.** During decisions, \`protected_slot\` produces a slot-specific flexibility term; final score reports call \`score(loadout)\` without protected slot (zero flexibility). Thus local decisions are **not** literally greedy ascent on the same scalar \`F(build)\` used to compare final builds. Audit/define consistent semantics before evaluating policy regret or expecting monotonicity.
4. **Scarce-role and assignment interactions.** The six pieces have exactly three normal affixes each and up to two exceptional. A strong single item can use exceptional capacity needed later for another role. To meet user's ideal requires explicit **allocation across slots**: CDT 2×50+, RD ≈95–100, MD ≈95–100, Triple 3–4 rolls totalling 90–100 effective, Mega 4–5 totalling 40–50; 4+5 Triple/Mega *with four defense rolls* is impossible (13 roles). Standard priorities are on EACH piece: AS and CD strongly desired, CC third, then Damage/Ranged, then Lifesteal/Block/Health. Since six pieces have exactly **18 normal slots**, AS+CD+CC on all six would consume all 18 and leave no room for Damage/Ranged etc.; these are preferences, not simultaneous hard requirements.
5. **Irreversibility and unknown future, not just a bad formula.** The live game watcher apparently requires immediate \`EQUIP\` or \`SELL\` and has **no proven stash/re-equip path**; rejected candidates are gone. Even a perfect hindsight six-item optimizer is **not an implementable online policy** without future knowledge. Any final six-item set from known future drops can be temporally constructed *with clairvoyance* by equipping each selected item when it appears (subject to actual game rules), but a real-time policy has to decide before knowing future offers. There is **no algorithm that guarantees the hindsight optimum for every possible future stream** under irreversible actions: two indistinguishable prefixes can need opposite choices. First verify the game's actual equip/sell/storage mechanics; do not assume a stash exists.
6. **Not enough to optimize one observed seed.** Manually raising rewards for one missing target oscillated between over-defense, weak Triple, weak Mega and junk normals across five 50k experiments. The fact that an offline alternative beats greedy already proves a missed opportunity; it does *not* prove every other variant of weighted scoring is best. Overfitting coefficients to seed \`20261011\` is not a solution.
7. **Offline MILP is an oracle/reference, not production policy.** \`OfflinePool.choose()\` maximizes a **linear proxy** under explicitly selected threshold/count constraints over a *prefiltered subset* (1,674), then reports production nonlinear score afterwards. Exact MILP optimality applies to the linear objective and its constraints only; the found \`+46.546\` is a **lower bound on possible improvement** over greedy for at least one attainable final build, NOT the proven best possible improvement/maximal Universal score. Do not call this a true global optimum.

### Recommendation — architectural direction for the NEXT chat (no implementation in this chat)

**Separate three problems:** (A) user-defined *desirability* of a finished outfit, (B) best feasible outfit from a *known pool* (hindsight benchmark), and (C) best **online** EQUIP/SELL policy with uncertain future and no storage. An offline solver cannot directly replace \`ItemComparer\` inside the live watcher.

**Stage 0 — validate mechanics, freeze baselines, establish definitions**

- Read \`src/domain.py\`, \`src/scoring.py\`, \`src/strategies.py\`, \`src/equipment.py\`, \`src/core.py\`, \`tools/simulate_strategy_loot.py\`, \`tools/offline_universal_benchmark.py\`, \`docs/offline-universal-50k-feasibility.md\`, \`docs/universal-target-calibration.md\`.
- Verify exact in-game choice mechanics: Does EQUIP instantly replace/destroy the old item? Is SELL irrecoverable? Is there an accessible inventory/stash, can the candidate be deferred, is an unequipped piece saved, can one switch between slots before next drop? Most important: does the currently equipped item/level affect future drops, and when is that applied? Do not design policies assuming unavailable controls. Treat unanswered mechanics as explicit assumptions.
- Freeze baseline \`seed=20261011\` and additional **holdout seeds**. Record exact code SHA and generator config for every experiment. Baseline: 41 EQUIP, final Universal 2837.077, PVE 1353.564. Keep \`4T+4M\` and \`3T+5M\` as separate modes. Define percent tolerance for “near 100,” whether effective Triple cap vs raw matters, and whether CDT per-roll >=50 is hard terminal requirement vs soft preference during growth.
- Define user objective as a typed, declarative \`UniversalTargetSpec\` + \`CoverageVector\` (suggested names, NOT yet implemented). Track two distinct CDT rolls, strongest individual RD and MD, number/quality of Triple and Mega rolls, their **effective capped totals**, per-item AS/CD/CC presence and roll quality, six-slot base-attack/health effects, actual PVE combat utility. Do not let 150% RD on two pieces satisfy “one RD ≈100.” Distinguish *deficit from target*, *value beyond threshold*, and *substitution potential*. Make terminal priorities explicit (e.g. feasibility/slack first, offense and normal affinities second, avoid junk; user can refine).
- Normalize what “better” means: user target satisfaction and component-wise distance; use production Universal \`score(loadout)\` as **one additional metric**, not sole truth. Evaluate PVE DPS/profile separately. A higher Universal scalar with worse target satisfaction is not automatically a success.

**Stage 1 — build a strong OFFLINE benchmark (measurement oracle)**

- Keep the 50k synthetic drops by stable IDs and six known slots, rerun baseline exactly; retain current MILP as a **proof of linear feasibility/infeasibility** and a source of guaranteed attainable candidates.
- For multiobjective/nonlinear terminal quality: build a **Pareto frontier** (coverage slack, PVE score, AS/CD/CC counts/quality, total strength) using role-aware candidate pruning per slot, dominance filtering and deterministic tie-breaking; consider MILP to enforce categorical role quotas + CP-SAT/MIP for linear indicators, then bounded beam/local-search/branch-and-bound evaluation of complete loadouts with the real \`BuildScorer\`. Do not claim global nonlinear optimality without exhaustive/certified bounds; report best-known objective and convergence.
- Compare three distinct reference policies: \`current online greedy\`; \`known-future offline final set\` (upper-bound/hindsight oracle; optionally replay exact chronology by equipping only the chosen drops when they appear); \`candidate improved online policy\` (no future knowledge). This separates model/roll scarcity, order/irreversibility, and decision-model regret. Report the six exact drops with IDs, normal/exceptional qualities and time order. Measure not merely final score but why a crucial item was sold on its arrival, the true original-slot score delta, what later drop completed its synergy, and the missed improvement.
- Existing verified artifact: [GitHub Actions 38207762735](https://github.com/yurii-zadryhun/dungeon-rush-loot/actions/runs/38207762735) / [JSON+MD 11727594427](https://github.com/yurii-zadryhun/dungeon-rush-loot/actions/runs/38207762735/artifacts/11727594427); permanent \`docs/offline-universal-50k-feasibility.md\`. Reuse instead of rediscovering.

**Stage 2 — research an actually deployable ONLINE decision rule**

- With **no stash**, the state is (six equipped items + fixed Wings/Cape, optional last-observed counters/beliefs, number of boxes remaining / estimated future opportunity). At each drop, only TWO actions: \`EQUIP candidate and lose previous\` or \`SELL candidate\`. A rollout should estimate \`Q_equip = E[terminal_utility | equip, plausible future drops]\` vs \`Q_sell = E[terminal_utility | sell, plausible future drops]\`. Estimate using a stochastic learned/calibrated drop model, common random numbers for the two alternatives, fixed compute budget, and an explicit terminal utility reflecting Stage 0 targets. Do NOT use the actual future drops of the benchmark seed to decide during replay (data leakage).
- Two reasonable implementable approaches to evaluate **against each other**, not blindly combine:
  1. **Fast role-aware policy / target-aware potential:** track missing exceptional roles, overfilled roles, remaining normal needs, and optional value of a high-quality rare roll; adjust the current decision so keeping a rare CDT/RD/MD/Triple/Mega slot-holder can be worthwhile despite a small present loss. Saturate satisfied roles and avoid double-counting redundant defenses. Ensure explicit precedence of target coverage over modest normal affix gains, *without* irrevocably rejecting a genuinely strong alternative in a partial build.
  2. **Finite-horizon rollouts / approximate dynamic programming:** sample plausible future offers, simulate both actions with a rollout policy, compare expected terminal metrics (plus uncertainty, deadline/remaining boxes), optionally cache/compress state and use limited beam search over reachable online states. An online “beam” of imaginary branches is only a planning approximation; **you cannot keep several candidate equipment states simultaneously in the actual game**. After the current action, discard hypothetical alternatives. Track complexity on PC and Android/Chaquopy before introducing it into Auto.
- Value of retaining options must be evaluated through likely future **complementary role supply**, not merely via \`_flexibility()\` stripping hypothetical affixes. For example, a high CDT piece with weak current normals may be a better bridge toward later Mega+Triple equipment than a currently higher-scored piece that duplicates a capped role. A \`+0.01\` immediate improvement threshold cannot capture that.
- Important caveat: current action comparison uses \`protected_slot\` and final benchmarks do not; decide whether to decompose **terminal utility** from online \`option_value(state)\`. Keep comparable (dimensioned and bounded) scales, deterministic cache keys and logs explaining \`current gain\`, \`target coverage impact\`, \`option value\`, \`future rollouts\` and \`decision confidence\`. Keep safety validation/OCR/touch unaffected.
- If a **stash is actually available**, the appropriate design changes materially: retain bounded nondominated candidates per slot, use online/offline reassignment to realize synergy across saved items, periodically select best feasible complete build. Confirm this before building a no-stash heuristic; don't invent a stash.

**Stage 3 — acceptance benchmark before enabling Auto**

- 50k \`20261011\` stream must still reproduce old greedy and confirmed offline 2883.623. Compare objective vector and all six item IDs; include known four-piece synergy witness as regression. Test minimum 20+ additional seeds (or a defined reliable sample) and 1k/10k/50k budgets, varying rarity, level and rolls; no seed-specific coefficients. Use the same stream for **synthetic** head-to-head policies; when modeling equipment-dependent future levels, use a game-faithful conditional generator with separate controlled evaluation.
- Metrics: terminal **target satisfaction vector** and weighted deficits (CDT2×50, RD>=90–95, MD>=90–95, Triple effective 90–100, Mega>=40), counts/quality of AS+CD+CC per item; PVE combat score, Universal score under a fixed evaluator, regret vs best-known offline candidate, rate of EQUIP, avoidable role loss, average decision latency and worst-case latency. Compare improvements against greedy not by self-referential score alone. Show distribution, median/worst cases and confidence intervals across seeds.
- Explicit regression scenarios: all individual swaps negative but paired swaps positive (the known \`+46.546\` example); incoming rare missing-role item vs high immediate-score redundant item; 2 CDT rolls 50/50 vs 66/34; strong RD 95 vs two weaker rolls; 3T+5M vs 4T+4M (including 12-slot budget); cap/overcap; AS+CD+CC pairing on same item; future stream with *no* complements; different horizon lengths; unknown stats/OCR errors remain CHECK; null/unavailable future distribution falls back to conservative bounded policy.
- Make the offline benchmark independent of implementation under test (avoid accidentally tuning optimizer's scoring and its own tests to match). Add deterministic fixtures/IDs, golden regression reports, differential tests against production \`ItemComparer\`, and performance bounds. Test that PVP/PVE behavior and Wings/Cape remain unchanged.
- **Only after independent benchmarks substantiate gains:** implement one shared-Python policy behind existing decision interface, allow rollback/toggle if needed, keep irreversible actions conservative, measure on PC replay before Android. No production policy modifications were authorized in this handoff step.

### Recommended very next operation in the next chat

1. Read this section and \`docs/offline-universal-50k-feasibility.md\`; check artifact from successful [38207762735](https://github.com/yurii-zadryhun/dungeon-rush-loot/actions/runs/38207762735) before modifying code.
2. Resolve **storage/irreversibility** and the user's precise priority ordering for close tradeoffs (e.g., 39.79% Mega vs slightly less PVE); do not overconstrain sparse synthetic streams.
3. Implement only the **analysis/reference tooling first**: offline Pareto/nonlinear best-known solver and trace/replay of the critical drops *at their actual arrival times*, then evaluate possible online policies. Do not promise an online policy can achieve the offline oracle with unknown future.
4. Preserve the user-validated PVE/PVP implementations and the desktop build; never optimize the benchmark by silently changing both its evaluator and policy.

**Scope of this 2026-10-12 handoff update:** documentation/analysis ONLY; no \`src/\`, \`tools/\`, tests, CI, Android, APK or live Universal scorer changed in this step.

---

## Historical — icon level OCR and diagnostic cleanup (2026-10-11)

User's latest live evidence: `session-20261010-213450-023.jsonl` and the
Divine [EXP] Celestial Helmet Lv87 vs Immortal [EXP] Dread Helm Lv4 screenshot.
At 21:35:16 and 21:35:31 the full-popup OCR captured both known titles
and all expected 5/4 affixes (including the exceptional rolls), **but not
a single level string for either card**. Python correctly returned CHECK.
Changing regex alone cannot parse pixels not returned by ML Kit.

Implementation:
- `runtime/IconLevelRecovery.kt`: derive two narrow icon-level ROIs from
  exactly two recognizable item-title rows; cover the label at the bottom of
  the icon (not adjacent affix text). Reject ambiguous/missing title anchors.
- `MlKitOcrAdapter.recognizeIconLevels()`: when general OCR fails on level,
  independently OCR each icon region at 4× in normal and light-on-dark modes.
  Accept only explicit, recognized `Lvl` text; no number guessing.
- `AndroidLootController.observe()`: when status is CHECK due to missing
  rarity/level after full-popup 2.5× and 3.5× passes, append actual recovered
  icon text and **rerun full Python validation/scoring**. If still unreadable
  or contradictory, remain CHECK and never Sell/Equip. Log icon level spans
  in `auto_ocr.observation` for follow-up.
- `tests/test_android_bridge.py`: reproduces the actual level-free 21:35
  lines; exercises 25 independent label combinations, one/missing levels,
  contradictions, corrupted labels and missing titles.
- `IconLevelRecoveryTest.kt`: checks anchored screen geometry for 709×1536
  and 1080×2340, 520 label forms, UI noise, ambiguous anchors and invalid
  screen dimensions.
- **Removed temporary one-shot debug**: no Auto tab controls, capture state,
  ZIP exporter, Android service wiring, snapshots or associated tests.
  `DownloadsLogExporter` is restored to JSONL exports only.

**Next:** Wait for final green Python+Android JVM tests, signed APK and release
SHA verification. Do not claim device efficacy from JVM/Python CI: only a new
live game check can show whether ML Kit reads the icon labels. If not, use
existing `auto_ocr.observation` JSONL for exact diagnostic spans. No
changes to scoring or Ultimate.

---

## Historical — forensic ZIP and exceptional marker regression (2026-10-10)

New user evidence:
- `dungeon-rush-ocr-debug-20261010-204511-851.zip`: `screen.png` (1080×2340), `ocr-crop.png` (810×983), `ocr-input.png` (2025×2458), `ocr.json`. **Crucial root cause:** full screenshot is the **Android Recent Apps overview**, showing Dungeon Rush only as a scaled task preview with unrelated other app cards. Bitmap crop from x=135..945 and y=936..1919 was correctly calculated but applied to **Recents preview**, not the live full-screen game, so game's outside-HUD text `Lvl 123` / `BX4` was inside the crop. Original horizontal offsets 0.125/0.875 are correct **for the full-screen game**, do not adjust them or mistake transformed OCR geometry for crop drift.
- `session-20261010-204852-442.jsonl`: previous first pass `SELL BACKPACK` had a valid Immortal **[EXP]** Infernal Tome with exceptional `+78.56% Ranged Defense`, but fresh pass returned `candidate: Immortal requires 0-0 exceptional affixes; parsed 1`. In game screenshot the actual candidate clearly shows the `[EXP]` marker and orange exceptional skill. A fresh OCR pass can omit a bracket or the entire token; blindly inferring EXP from skill presence is not permitted. It also showed level OCR `LU1O6` / `LU 106` for Lv106.

Implemented:
- `runtime/ForegroundWindowGate.kt`: selects only a single focused *application* window; rejects ambiguous active windows. No stale previous Accessibility-event package fallback. `AccessibilityAdapters.kt` reads focused windows with `flagRetrieveInteractiveWindows`; tap adapter independently rechecks game focus immediately before gesture. `StableForeground.kt` requires game focus to settle for 800 ms before capture or Auto; controller still validates foreground during decision process.
- `src/affix_rules.py`: `EXP_MARKER_RE` tolerates a standalone `EXP` token with missing `[` or `]`, but does **not** synthesize the marker when completely absent. Fresh Auto observes ONE additional real frame only if previous validated result was OK and fresh OCR had the specific exceptional `0-0` error. The extra observation must match full original semantic item key/action or CHECK/no tap.
- `src/parsing.py`: explicitly accepts `LU1O6` and `LU 106` and converts O→0 ONLY inside a tagged level token; affix number digits stay strict.
- Python regression tests in `tests/test_rarities_and_exp.py` and `tests/test_android_bridge.py`: partial EXP markers on original Infernal Tome, exact affixes and level OCR. Tests assert wholly missing EXP remains CHECK.
- Android JVM `ForegroundWindowGateTest.kt`, `FreshVerificationTest.kt`: Recents with stale game task, focus changes/settling, rejection of ambiguity, bounded retry semantics.

**Pending verification:** check Python CI + Android JVM/Gradle/signature and verify rolling release `android-live-latest` SHA matches the code from this investigation. Do not imply build is green until verified. Then install, open popup, switch back into FULLSCREEN game, wait for window settle; export another one-shot ZIP if anything still fails. Keep scoring/Ultimate unchanged.

---

## Historical — temporary one-shot OCR diagnostic (removed 2026-10-11)

The user confirmed the original 0.125/0.875 horizontal crop exactly matched
the game popup in their source screenshot (709x1536). Earlier claims that
visible background `Lvl 123` / `x4` pixels were inside the crop were wrong:
those elements are outside the source crop. Source-frame vs ML Kit-input
diagnostics are needed; do **not** blindly tighten the crop or remove more
text in the parser.

**Implemented in android-live:**
- `runtime/OcrDebugCapture.kt`: ephemeral, one-shot state machine
  Idle→Armed→Capturing→Saved/Failed, cancel/retry; no persistent screenshots.
- `runtime/AndroidLootController.kt` checks debug capture **before** normal
  Auto and independently of Auto enabled, only when the target game is in
  foreground. This code never reaches the touch path. Captures one frame and
  runs regular 2.5× ML Kit OCR and optional Python evaluation; logs result.
- `runtime/MlKitOcrAdapter.kt` captures `ocr-crop.png` and `ocr-input.png`
  from the **actual bitmaps** passed to OCR, not reconstructed/simulated input.
  Shared `OcrCropPixels.kt` calculates tested integer boundaries.
- `data/OcrDebugExporter.kt` bundles `screen.png` (Accessibility full
  bitmap), `ocr-crop.png` (source crop), `ocr-input.png` (exact scaled input),
  `ocr.json` (source dimensions, pixel+relative crop, OCR lines and parser
  decision/errors). Uses MediaStore Downloads ZIP via extended
  `DownloadsLogExporter.kt` with IS_PENDING and rollback.
- Auto tab has **Capture next game OCR as ZIP** (requires Accessibility
  connected and Auto STOPPED), shows status/file name and Cancel.
  Instructions: leave the loot popup open in the game, arm from this app, then
  return to Dungeon Rush. One-shot ZIP is saved automatically in Downloads,
  without a picker; user then shares ZIP. Warn about visible identifying
  information in the full screenshot.
- `runtime/OcrDebugCaptureTest.kt`: JUnit tests for one-shot semantics,
  cancellation, crop pixel rounding on 709×1536 and 1080×2340, valid/invalid
  crops and ZIP entry integrity. Existing Python crop-geometry test also
  covers original relative offsets.

**Verification pending as of this handoff update:** latest Android release
must pass all Python and Android JVM tests and Gradle release signing, and
`android-live-latest` must reference the latest production SHA. Do not
give the user an earlier rolling APK as if it includes diagnostics. Test on
device by exporting the ZIP of an actual two-item popup. Note that this
capture is triggered on the first game-foreground frame, so user must ensure
the popup is already open before returning to the game.

**Deferred:** no modifications to tier/level scoring, Ultimate rules,
or integration with `dungeon-rush-simulator`.

---

## High-level architecture

One Python decision domain, two platform shells:

```text
                         shared Python
                   parser / equipment / scorer
                     strategies / decisions
                        /             \
                       /               \
Desktop                                       Android
ADB screenshot                               Accessibility screenshot
PaddleOCR                                    ML Kit OCR
ADB gestures                                 Accessibility gestures
JSON equipment                               Android local storage
Rich/console                                 Compose UI
JSONL decision logs                          JSONL session logs + UI
```

Important shared modules include:

- `src/domain.py`
- `src/config.py`
- `src/text.py`
- `src/parsing.py`
- `src/equipment.py`
- `src/scoring.py`
- `src/strategies.py`
- `src/core.py`
- `src/events.py`
- `src/ui_geometry.py`
- `src/equipment_import.py`
- `src/game_catalog.py`
- `src/android_bridge.py`

Android embeds the same Python code through Chaquopy. Do not duplicate scorer/parser rules in Kotlin.

Android runtime adapter boundary already exists for screen capture, OCR, touch and foreground app detection. The screenshot interface was deliberately designed so MediaProjection can be added later without changing shared logic/controller/UI.

## Equipment/build model

Tracked slots are now **8**:

1. weapon
2. helmet
3. backpack
4. gloves
5. necklace
6. ring
7. wings
8. cape

Build scoring must aggregate all eight because Wings/Cape contribute stats.

### Standard gear

The first six slots use the rarity/level primary-stat model and exact rarity-specific rolled-affix composition (see current TODO).

Do **not** infer the slot from English semantics like “helmet”, “backpack”, etc. The game has misleading names:

- `Celestial Lyre` -> backpack
- `Infernal Tome` -> backpack
- `Radiant Shield` -> backpack
- `Blessed Tiara` -> helmet
- `Undying Mask` -> helmet
- `Eternal Cape` -> helmet
- `Celestial Lightning` -> weapon

The current solution uses a catalog extracted from the supplied game APK/Unity serialized assets. `src/game_catalog.py` contains the name -> slot mapping (hundreds of EquipmentData definitions). Keep catalog-based classification as the authority.

### Wings

Example current Wings screenshot:

- rarity: Divine
- title: Eternal
- level: 100
- absolute primary Damage: 2.25M
- absolute primary Health: 7.50M
- five rolled affixes

Wings are structurally identified by both absolute Damage + Health primaries plus a known Wings name. They have their own progression constants in the extracted game data; level can be inferred from primary values when OCR misses the level.

### Cape / Cloak

Example current cape:

- title: Divine Cloak
- rarity marker: `[Mythic]`
- level: 31
- fixed/intrinsic `+80% Damage`
- fixed/intrinsic `+80% Health`
- rolled affixes: `+33.25% Critical Damage`, `+8.89% Critical Chance`

Important: Cape Damage/Health are **not rolled affixes**. They are intrinsic cape stats which scale with cape level. They belong in build aggregation, but must remain separate from `stats` (rolled affixes).

Game data for cape/wings also exists in `dungeon-rush-simulator` and was used to derive progression/affix behavior.

## Scoring

Three strategies exist:

- `universal`
- `pve`
- `pvp`

Scoring is build-aware, not item-isolated. It evaluates replacing the slot in the entire loadout, including caps/overcaps and interactions.

Important design requirement: do not treat a candidate’s stat as mostly worthless merely because the current total is capped. A higher roll may enable replacing a weaker stat source in another slot later. Existing flexibility/look-ahead scoring was introduced for this reason.

PvP direction discussed:
- very high value: Critical Damage Taken, defenses, Triple Hit, Attack Speed
- Double Hit loses marginal value as Triple Hit grows
- useful but not blindly stacked Lifesteal
- crit-oriented offensive stats lose value if opponents commonly have CDT around -100%

PvE direction discussed:
- Triple Hit, Attack Speed
- Mega Crit, with Crit Chance declining in value as Mega Crit coverage grows
- Crit Damage
- Double Hit declines as Triple Hit grows

**Historical description:** the current Universal is PVE-first with explicit target-role coverage; see CURRENT PRIORITY above.

## OCR / textual fuzzy matching

Numeric data must stay strict. Do not fuzzy-match numbers.

Good:
- regex/range/known progression recovery for `Lvl`, percentages, K/M values
- known special correction such as OCR `Lv134` -> real `Lv34` only when the impossible range proves the leading `1` is OCR noise
- Wings/Cape progression-based recovery where the game formula makes it safe

Bad:
- Levenshtein/fuzzy matching numeric values

Text labels **should** use OCR-aware fuzzy matching.

`src/text.py` has/was being changed to use weighted Levenshtein for names such as:

- `Attack 5peed` -> `Attack Speed`
- `Dread Neck1ace` -> `Dread Necklace`

OCR-confusable substitutions (e.g. 0/o, 1/l, 1/i, 5/s) have reduced edit cost. Item-name matching also uses confidence threshold + margin to the second-best candidate. If ambiguous, fail closed.

## Android equipment screenshot import

User wants to select the 8 current-equipment screenshots in any order and have the app identify all slots automatically.

For the current device/screenshots, the item modal is effectively the same size/static position. We intentionally use static crops for now. Later, when the product is considered ready, replace this with robust popup/layout detection for multiple devices/resolutions.

Critical constraint: aggregate build stats are visible behind/below the item popup. OCR must stay inside the foreground item modal so those background stats cannot be mistaken for affixes.

Current import stack:

- Android selects images
- `EquipmentScreenshotImporter.kt`
- fixed main crop
- ML Kit line OCR with upscaling / multiple passes
- separate tight high-scale level crop because outlined `Lvl` text is difficult
- shared Python `EquipmentScreenshotParser`
- APK-derived item catalog for standard-slot detection
- structural/canonical detection for Wings/Cape
- review dialog before saving

The import is **still the main broken area**. User’s latest real test still produced failures:
- Wings: slot detected, but level not parsed
- Helmet: slot detected, but level not parsed
- Weapon: level not parsed and only 3 affixes parsed
- Cape: slot/title/level parsed, but one fixed Damage/Health line was missed, producing “Cape primary Damage/Health lines were not parsed safely.”

Screenshots/results from the conversation showed that ML Kit gets most text but occasionally drops outlined level text and individual rows. Do not assume parser logic alone is the issue; capture raw OCR diagnostics from every pass.

Recent importer work added:
- APK catalog instead of keyword slot guessing
- line-level ML Kit OCR
- upscaled 2.5x/3.5x main passes merged by physical row
- dedicated 3.5x/5x level OCR passes
- Wings level inference from primary progression
- Cape intrinsic recovery based on known cape progression
- OCR-aware Levenshtein for item/affix names

The next useful debugging input must be an exported application diagnostics log, not another screenshot of the review dialog.

## Logging design

There are two intentionally separate log concepts.

### 1. Loot/session logs

These contain only an Auto loot session and remain one JSONL file per session.

- Start Auto -> create new session file
- append each event immediately and fsync; never buffer until Stop
- Stop Auto -> close session
- old session files remain selectable
- active session is automatically selected in the viewer
- UI loads 50 newest entries and loads 50 more while scrolling

Do not put unrelated app/import errors in these files.

### 2. Global application diagnostics log

This was the latest requested feature and implementation is partially/mostly committed on `android-live`.

Purpose: one persistent application-level JSONL containing diagnostics unrelated to a loot session, especially equipment screenshot import debugging.

Expected categories/events include:
- app lifecycle/startup
- Accessibility service lifecycle/errors
- controller/runtime failures which are application-level
- equipment import started/completed/failed
- validation failures
- per-screenshot result
- raw OCR data for each OCR pass (main/level, scale, recognized text/boxes/confidence)
- exceptions + stack traces

Requirements from user:
- separate from session logs
- persistent across app launches
- write immediately
- on Logs page: dedicate **one row** to “Application log”
- put an export/download action at the end of that row
- export the raw log file so the user can attach it in the next chat

Recent commits added files/wiring around:
- `ApplicationLogStore.kt`
- application log port
- import diagnostics
- per-pass OCR diagnostics
- accessibility lifecycle logging
- controller failure mirroring
- export row on Logs screen
- app/process startup logging

Verify the current implementation after fixing Android compilation. In particular, confirm exported JSONL contains enough OCR-pass detail to reproduce why each screenshot failed.

## Android home-screen UX request

On the Auto/home screen there are two status cards:

- Accessibility service
- Equipment

User explicitly requested inline actions **inside these cards, at the end of the row/card**:

- Accessibility card -> button/action opens Android Accessibility settings
- Equipment card -> button/action switches directly to the Equipment tab/screen

Recent commit `feat: add inline home status actions` attempted this. Current Android compilation failure is in the UI around `weight`, so verify these cards after fixing imports/layout.

Do not keep a redundant full-width “Open Accessibility settings” button if the inline card action already covers it cleanly.

## Android Auto lifecycle

Auto mode is explicitly Start/Stop.

AccessibilityService may remain enabled/connected after Stop, but automation should do nothing while Auto is disabled.

A process restart must not silently resume auto-tapping. User must explicitly Start again.

## Historical — earlier live session OCR failures (2026-10-10)

User reported session `session-20261010-194809-529.jsonl` with five CHECK OCR events at 19:48–19:49; compared real `ocr_lines` (text, confidence and screen boxes) to `android-live`.

**Distinct causes and fixes:**

1. Equipped Gloves Lv124 could parse as null (displayed `Lv0`) or erroneously 123. ML Kit recognized `LvI 124 +7.32% Ranged Damage` or `Lv0124 +7.32% ...`, while a **separate, unrelated HUD label** `Lvl 123` sat far to the right of the equipment popup. `LootItemParser._level` now accepts the narrowly observed `Lv0124` spelling and ignores standalone levels outside the affix-text horizontal boundary. Two conflicting *in-card* levels still yield CHECK. `LogsUi.kt` shows `Level unreadable`, not `Lv0`, when a level really is missing.
2. Candidate Ancient Winter Gloves sometimes had `Lvi 51 +8.54% Attack Speed BSX4` or `Bx4`. The trailing game's `x4` badge was accidentally included as part of the stat label. `_clean_label` removes **only** this explicitly recognized trailing badge, not arbitrary letters/numbers.
3. `-44.78% Critical Damage` + separate `Taken` appeared in equipped Dread Necklace; `-39.40% Critical Damage` + `Taken` in Crimson Backpack. Title splitter wrongly glued `Taken` to the following full candidate title, discarding the essential affix suffix from the equipped card. Now complete catalog titles are accepted on their own, and wrapped-title logic does not steal the preceding text. The stat continuation correctly restores `critical damage taken`.
4. `(LvU 106) -5.26% Companion Cooldown` is another narrowly recognized level OCR spelling, tested in the Backpack case.
5. The 19:49:53 event had *zero OCR spans* and appropriately yielded CHECK/no tap; no action warranted without actual loot text.

**Regression coverage:** `tests/test_android_bridge.py` adds four comprehensive cases replaying the logged Gloves (both level spellings, both badge spellings and right-side HUD level), Necklace, Backpack and true in-card level conflicts. They go through the full Android JSON bridge, validate the parsed affixes/levels/slot and require a verified decision where appropriate.

**Verified:** **92 Python tests** pass on both 3.11 and 3.12, run `38082125040`. Android workflow `38082125026` green: shared Python, JVM tests, signed APK, signature, publish. Rolling release `android-live-latest` targets exactly `fade8fef74e47edef9e3af0feb71aef29efb5321`, file size 53,859,985 bytes.

APK: https://github.com/yurii-zadryhun/dungeon-rush-loot/releases/download/android-live-latest/DungeonRushLoot.apk

**Next:** Install and retest live on device. Fail-closed if new OCR patterns arise; export Application log raw `auto_ocr.observation` and relevant session logs. Future tier/level scoring calibration and `dungeon-rush-simulator` reference remain deferred. Ultimate is not currently available.

---

## Previous milestone — uploaded log audit completed (2026-10-10)

The user provided actual exported files:
- `session-20261010-190130-547.jsonl`: 5 records: session start and four SELL/GLOVES decisions, all cancelled by old "loot changed during fresh verification".
- `dungeon-rush-app-log.jsonl (3)`: 151 events, including 9 Auto OCR observations and 2 historical import-validation failures.

### Findings

1. **Previously fixed:** the import at 18:57:54 had 7/8 success; **only** Ring failed due to `+9.07%% Mega Crit Chance`. The shared parser now handles repeated percent glyphs; regression test with exact real Void Ring OCR exists.
2. **Previously fixed:** four unsuccessful SELL/GLOVES fresh verifications at 19:01 had equal semantic candidates and equipped items but changing OCR `raw_text` and `confidence`, confirming that old `DecisionEvent.candidateKey` was unstable. This is already fixed by `src/verification.py` and the Kotlin consumer of `verification_key`.
3. **Additional observed OCR case, fixed in this audit:** at 19:01:55 the live parser returned CHECK because ML Kit recognized `LvI 124 •7.32 Ranged Damage`; a bullet replaced + and the % was absent. In `src/parsing.py`, `LEVEL_ROW_BULLET_SIGN_RE` now recovers ONLY leading `•`/`·` from an OCR row that also contains a valid explicit level marker and intact 1–2 decimal digits. The normal stat's permitted sign and upper cap still apply. It does not infer arbitrary signs or repair numbers. `tests/test_android_bridge.py` exercises a full Gloves Auto two-card OCR-to-decision flow with the actual recorded data, plus malformed/negative cases.
4. Also fixed APK workflow trigger: test-only commits under `tests/**` now trigger a new Android build. Previously a source-only build was green but release skipped because the branch advanced to a test-only commit before publication.

### Verified

- Python CI: **88 tests passed**, Python 3.11 and 3.12, GitHub run `38080621075`.
- Android workflow: **success**, run `38080621076`, including shared Python tests, Android JVM tests, Gradle signed APK, signature verification and prerelease publish.
- Verified rolling release `android-live-latest` SHA is **`68a82c66fc3cc8ac36d95b4aa476c9d1dfc74c6a`**, exactly matching the successful Android source SHA; release `DungeonRushLoot.apk` is 53,859,981 bytes.
- APK link: https://github.com/yurii-zadryhun/dungeon-rush-loot/releases/download/android-live-latest/DungeonRushLoot.apk
- **Real-device behavior for this new OCR variant is not yet retested.** It should now parse the logged `•7.32` safely, but the next device run is the empirical validation.

### Follow-up

Test the same alt/primary game popup. If Auto still returns CHECK or cancels, export Application log JSONL so `auto_ocr.observation` and `auto_verification.fresh_check_rejected` show the actual next cause. Do NOT revisit rarity/level scoring, `dungeon-rush-simulator` integration, or Ultimate placeholder in this bugfix.

---

## Previous milestone — OCR percent + fresh verification fixed (2026-10-10)

### Device reports and root causes

1. Import of the actual Immortal [EXP] Void Ring failed because ML Kit rendered `+9.07%% Mega Crit Chance`. In the shared parser's `STAT_NUMBER_RE` only one literal `%` was permitted, so a doubled glyph made the entire stat unreadable and caused an unparsed-affix issue.
2. Auto logged repeated `SELL · GLOVES` with `Auto cancelled: loot changed during fresh verification`, despite the visible popup not changing and repeated displayed scores. The Android `DecisionEvent.candidateKey` included JSON-serialized `stats` arrays with `raw_text` and `confidence`, so harmless differences between OCR frames changed the supposedly stable identity key.

### Implemented and verified

- `src/parsing.py`: recognizes repeated `%` separators, including `%%`, `%%%` and `% %` without changing numeric digits or caps. `tests/test_equipment_import.py` reproduces the exact ring import + malformed numeric negatives.
- `src/verification.py`: deterministic semantic SHA-256 key for the **complete pair** of equipped/candidate items with normalized catalog names/slot, rarity, tier, level, [EXP], melee flag and sorted canonical affix name+two-decimal value pairs. Ignores raw OCR strings, confidence, span geometry, and affix order. Cannot produce a key on CHECK or unrecognized/wrong-slot titles.
- `src/android_bridge.py` emits `verification_key`. `Models.kt` uses **only that validated key**, instead of reserializing OCR `stats` metadata. Null/missing key always means no tap.
- `runtime/FreshVerification.kt` differentiates OCR-inconclusive, action/slot changes and semantic item-identity mismatches. `AndroidLootController.kt` still requires two independent OK passes with same semantic key and action and logs structured `auto_verification.fresh_check_rejected` diagnostics instead of a misleading generic 'loot changed'.
- `tests/test_fresh_verification.py` includes end-to-end two-pass OCR with differing confidence, line order and percent glyph, plus checks that actual item/roll/level/rarity/EXP changes are not treated equal. Android JVM `FreshVerificationTest.kt` tests stable key usage and fail-closed behavior.
- GitHub Python CI **success**, run `38079699127`, **87 tests**, both Python 3.11 and 3.12.
- GitHub Android workflow **success**, run `38079699155`, source commit `a4d9821cd8f7b426150a70f04a2dcb3c42814357`. All 87 shared Python tests, Android `testReleaseUnitTest`, signed release APK build, signature verification, artifact upload, and rolling prerelease publication passed. Verified `android-live-latest` points at that exact SHA and has `DungeonRushLoot.apk` (53,859,985 bytes).
- Direct APK: https://github.com/yurii-zadryhun/dungeon-rush-loot/releases/download/android-live-latest/DungeonRushLoot.apk

### Next user/device steps

- Install the new APK; retry importing the same eight screenshots, especially Void Ring with duplicated percent.
- Re-test Auto SELL in-game with an unchanged Gloves popup. It should proceed after two semantically identical OK decisions (assuming target and other safety checks succeed).
- If another verification rejects, export the **Application log** JSONL and locate category `auto_verification`, event `fresh_check_rejected`: it now includes first/fresh status, action, slot, semantic keys and fresh OCR error message. This will distinguish actual mismatch from unreadable second pass.
- No claim has yet been made that the APK is tested on-device for these two fixes.

### Future only — do not implement without explicit request

- Revisit rarity/tier/level/primary stat score weights for all newly supported lower rarities. Earlier linear calibration assumed Immortal Lv1 approximately -20 points to Divine Lv130 approximately +15; now its extrapolation needs separate analysis. **Do not modify scoring in this bugfix.**
- For combat and item mechanics use the existing `yurii-zadryhun/dungeon-rush-simulator` repository as a reference when genuinely needed, not proactively for these two fixes.
- `Ultimate` is a prerelease placeholder (not currently obtainable in the game); keep it fail-closed/unconfigured. No need to ask the user for a currently unknowable count.

---

## Previous milestone — rarity-exact model (2026-10-10)

### Confirmed user rules

- Common, Uncommon, Rare, Epic: **exactly 1 NORMAL** rolled affix.
- Legendary, Mythic, Artifact, Ancient: **exactly 2 NORMAL** rolled affixes.
- Immortal, Divine: **exactly 3 NORMAL** rolled affixes.
- If the title contains [EXP], add **1 or 2 EXCEPTIONAL** rolled affixes; otherwise exactly 0 exceptional. Normal count does **not** decrease for EXP. Total is 1–5.
- `Ultimate` exists in the catalog but user did NOT provide its affix count: fail closed, do not infer from tier.
- Observed **Divine Eternal Wings without EXP has 5 normal affixes** and absolute Damage/Health primaries. This is a verified slot-specific exception. Cape's fixed primary Damage/Health percentages are not rolled affixes.
- Semantic limitation: loss of an entire second exceptional OCR line makes a 2-exceptional item observationally identical to a valid 1-exceptional item. Visible damaged lines and missing normal affixes are detectable; don't pretend rarity determines 1 vs 2.

### Implemented

- `src/config.py` owns `RARITY_NORMAL_AFFIX_COUNT`, exceptional count range (1–2), `MIN_STATS=1`, `MAX_STATS=5`.
- `src/affix_rules.py` has centralized `affix_requirement(rarity, title, slot)` and `validate_affixes(title, stats, rarity=, slot=)`. Checks exact ordinary count, 0 vs 1–2 exceptional, duplicate/unknown names, range and sign; unknown Ultimate fails closed.
- `src/equipment.py` enforces model during persisted JSON validation. `src/equipment_import.py` enforces model during each screenshot import. `src/scoring.py` validates both equipped/candidate live OCR items before Sell/Equip, checking raw suspicious stat lines first.
- Android `app_config_json()` schema **4** includes `rarity_normal_affixes`, `exp_exceptional_bounds`, `divine_wings_normal_affixes`, and absolute `affix_bounds` 1–5. `Models.kt` parses these fields; `EquipmentUi.kt` editor uses dynamic count bounds for selected rarity/title, shows expected ordinary/exceptional split, and blocks Ultimate when no rule exists.
- The broader Logs browser/detail and one-click Downloads exports remain, as do 2.5×/3.5× OCR and `auto_ocr.observation` logging.
- `tests/test_rarities_and_exp.py` rewritten with complete all-rarity×all-slot×EXP matrix, off-by-one counts, missing affixes, OCR, Ultimate, Wings/Cape, Android schema and live low rarity scenarios. Existing regression tests and source fixtures updated for exact counts. Crucially, test for 2→1 lost exceptional acknowledges unavoidable ambiguity.

### Verified CI and next action

- **Python CI success** on `806bdd1f`, GitHub Actions run `38078441935`: **79 tests**, both Python 3.11 and 3.12. Some earlier CI runs failed for a regex escaping bug and tests that incorrectly assumed second exceptional loss was always detectable; both addressed.
- **Android APK verified successful:** run `38078660399` on source SHA `706b7b3657bc8f23b3800b3d6dacf059dc6f4c7d` completed successfully. Shared Python tests, Gradle assembleRelease, apksigner verification, artifact upload and rolling prerelease publication all succeeded. Verified `android-live-latest` release `target_commitish` equals that exact source SHA and includes `DungeonRushLoot.apk` (53,843,601 bytes).
- Direct APK: https://github.com/yurii-zadryhun/dungeon-rush-loot/releases/download/android-live-latest/DungeonRushLoot.apk
- **Device validation pending:** install new APK, **re-import existing equipment** so the actual [EXP] markers are retained, test a 1-affix Common/Rare, 2-affix Legendary/Mythic, 3-affix Immortal/Divine and EXP1/EXP2 item, plus Logs→Application log→Export. If any CHECK, attach the new `auto_ocr.observation` application JSONL. No device-success claims yet.
- `Ultimate` count remains unverified; request that specific rule from the user before enabling automation for it.

## Useful game/reverse-engineering context

A separate simulator repo exists: `yurii-zadryhun/dungeon-rush-simulator`.

The user supplied current game files/XAPK/APK plus Cpp2IL output. Unity serialized assets proved more useful than Cpp2IL for item-name/slot catalogs.

Relevant extracted facts:
- ordinary equipment definitions expose item/display names and slots
- Cape and Wings have distinct data/progression
- item naming cannot safely infer slot semantically
- current game package: `com.lavalabs.dungeonrush`

## Safety behavior for automation

Before any Auto tap:
- game must be foreground
- fresh screenshot/OCR must still describe the same candidate
- action must be unchanged
- uncertainty -> CHECK/no tap

After Equip, update persisted equipment only after visual evidence that the UI changed.

There is an older known weak point around sell-confirmation handling: the current implementation historically used a rarity-based “Sell then Confirm” assumption rather than robustly detecting the confirmation modal. Do not expand this while debugging import unless needed, but it remains a future hardening item.
