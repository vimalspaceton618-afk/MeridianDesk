# External research workers

Launch the workers from Meridian Desk's integrations view after loading at least 32 OHLC bars. They use up to the latest 256 bars in the selected feed. The source checkout, model weights, dependencies, runtimes, caches and research data live on E:.

| Component | Pinned upstream | Local role |
| --- | --- | --- |
| TradingAgents 1.0.1, Apache 2.0 | [121265d](https://github.com/TauricResearch/TradingAgents/tree/121265d18d467ac717f7af99cb0d669c15d2e73c) | Source-built Windows CLI provides an on-demand research report through a configured LLM. The E: Node runtime runs its official headless entry point. |
| Kronos, MIT | [67b630e](https://github.com/shiyu-coder/Kronos/tree/67b630e67f6a18c9e9be918d9b4337c960db1e9a) | Local model projects a next-interval close from historical OHLC. Its forecast assumes the market stays open through the inferred interval. |
| Ruflo 3.80.8, MIT | [48b04dc](https://github.com/ruvnet/ruflo/tree/48b04dce286a1df4af0411923821cf63399d7c8b/v3/%40claude-flow/swarm/src/coordination) | The upstream event bus, agent registry and task orchestrator schedule three deterministic risk calculations, then release the dependent review task. |

## TradingAgents settings

When you click Run for TradingAgents, it sends the symbol, as-of time, bar count, starting and ending closes, low and high to the configured provider. It can request outside research data. Upstream account sync is disabled. Sessions live in `E:\MeridianDesk\data\tradingagents`. The report retains the upstream source list when the model cites sources. Runtime limits are 60 seconds and 30,000 aggregate tokens per question. A partial report is marked in the output. Provider prices and quota apply.

Configure one provider's environment key, or set `TRADINGAGENTS_MODEL` to a specific provider/model when using several providers. For a compatible local server, set `TRADINGAGENTS_BASE_URL` to its API base URL and `TRADINGAGENTS_MODEL` to its model ID before launching the desk. The server must support streaming chat completions and tools. The app recognizes provider configuration on startup. Successful authentication is checked when running research. See the [pinned model documentation](https://github.com/TauricResearch/TradingAgents/blob/121265d18d467ac717f7af99cb0d669c15d2e73c/docs/models.md).

## Installed files

The CPU model uses PyTorch 2.8.0+cpu, pandas 2.2.2, NumPy 1.26.4, einops 0.8.1, huggingface_hub 0.33.1 and safetensors 0.6.2. Both MIT-licensed checkpoints are downloaded to `models` and loaded in offline mode. The model forecasts a mean across five sampled paths, with a fixed seed for repeatable inspection. Checkpoint revisions are [Kronos-mini f4e6869](https://huggingface.co/NeoQuasar/Kronos-mini/tree/f4e68697d9d5aed55cef5c96aabc3376bcad9f81) and [Kronos-Tokenizer-2k 26966d0](https://huggingface.co/NeoQuasar/Kronos-Tokenizer-2k/tree/26966d0035065a0cae0ebad7af8ece35bc1fb51c).

Ruflo's three included runtime modules are compiled from the pinned repository. Each run uses an in-memory registry scoped to that analysis. Node 24.14.1 serves both JavaScript workers. Upstream licenses accompany their source trees.

## Verification

From `E:\MeridianDesk`, run `.\runtime\python\python.exe -B tests\test_integrations.py -v`. The suite exercises real local CPU inference, the dependency-driven Ruflo review and TradingAgents end-to-end using a loopback model-protocol fixture. It does not contact a paid model during testing.
