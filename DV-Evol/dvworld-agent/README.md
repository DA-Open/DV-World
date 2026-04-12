# Spider Agent Quickstart

This is the sibling baseline we use during development; it produces a single, image-rich report (contrast with `da-agent`, which uses a three-stage flow for tighter control). You can (and should) refine the system prompts to better guide your model for your use case.

1) **Download datasets**  
   Follow `../dacomp-da/README.md` to download:
   - English: `../dacomp-da/tasks/dacomp-da.jsonl`
   - Chinese: `../dacomp-da/tasks_zh/dacomp-da-zh.jsonl`

2) **Configure your LLM**  
   Update model endpoints/keys in `spider_agent/agent/config.py` as needed.

3) **Install dependencies**  
   ```bash
   pip install -r requirements.txt

   python3 -m pip install -r requirements.txt
   ```

4) **Run the agent**  
   `-s` sets the experiment suffix (output subfolder), `-t` points to the task JSONL.
   ```bash
   # English example
   python3 run.py --model openai_qwen3-coder-plus -s both1 -t ../../dacomp-da/tasks/dacomp-da.jsonl
   # Chinese example
   python3 run.py --model openai_qwen3-coder-plus -s try1-zh -t ../../dacomp-da/tasks_zh/dacomp-da-zh.jsonl --language zh
   ```
Common flags:
- `--example_index`: index range (e.g., `0-10`, `2,3`, or `all`)
- `--example_name`: filter by substring in task id
- `--language`: `zh` (default) or `en`
- `--overwriting` / `--retry_failed`: control reruns when outputs exist

5) **Export results to the evaluation suite**  
   Collect a run’s outputs into `../dacomp-da/evaluation_suite/agent_results/`:
   ```bash
   python3 get_results.py openai_qwen3-coder-plus-test1-zh --output_dir ../../dacomp-da/evaluation_suite/agent_results
   python3 get_results.py gemini-2.5-pro-both1 --output_dir ../../dacomp-da/evaluation_suite/agent_results
   ```




{
    "truncation_override_config": {
        "default": {
            "steps": 4096,
            "steps_strategy": "extension",
            "steps_extended": 0
        }
    },
    "external_api": {
        "provider": "general",
        "model": "model",
        "url": "sd://inf.unified_server_qwen_tc.qwen3coder_3.service.hl/v1/chat/completions",
        "base_url": "sd://inf.unified_server_qwen_tc.qwen3coder_3.service.hl/v1/",
        "extension_max_tokens": 512,
        "generation_config": {
            "max_tokens": 4096
        },
        "http_timeout": 3600,
        "proxies": null,
        "retryable_error_codes": [],
        "retryable_error_msg_keyword": [],
        "skippable_error_codes": [400, 500],
        "skippable_error_msg_keyword": []
    }
}




python3 run.py --model qwen3-coder-30b-a3b -s try3 -t ../../dacomp-da/tasks/dacomp-da.jsonl --workers 1 --language en

python3 run.py --model qwen3-coder-30b-a3b-api -s try1 -t ../../dacomp-da/tasks/dacomp-da.jsonl --workers 1 --language en

python3 run.py --model qwen3-coder-30b-a3b -s try5 -t ../../dacomp-da/tasks/dacomp-da.jsonl --workers 20 --language en

python3 run.py --model serve_dacomp_da_gemini3_pro_4356_qwen_test2 -s try2 -t ../../dacomp-da/tasks/dacomp-da.jsonl --workers 20 --language en

python3 run.py --model serve_dacomp_da_gemini3_pro_4356_qwen_test2 -s try3 -t ../../dacomp-da/tasks/dacomp-da.jsonl --workers 20 --language en

python3 run.py --model serve_dacomp_da_gemini3_pro_4356_qwen_test2 -s try4 -t ../../dacomp-da/tasks/dacomp-da.jsonl --workers 20 --language en

python3 run.py --model doubao-seed-1-6-thinking-dataagent-preview -s try3 -t ../../dacomp-da/tasks/dacomp-da.jsonl --workers 1 --language en

python3 run.py --model doubao-seed-1-6-thinking-dataagent-preview -s try4 -t ../../dacomp-da/tasks/dacomp-da.jsonl --workers 1 --language en



python3 run.py --model serve_dacomp_da_gemini3_pro_4356_qwen_test1_step_408 -s test1222_1 -t ../../dacomp-da/tasks/dacomp-da.jsonl --workers 1 --language en

python3 run.py --model serve_dacomp_da_top_trajectories_doubao1221_test2_step_1330 -s test1223_1 -t ../../dacomp-da/tasks/dacomp-da.jsonl --workers 20 --language en

python3 run.py --model qwen3-coder-30b-a3b -s test1222_1 -t ../../dacomp-da/tasks/dacomp-da.jsonl --workers 10 --language en


python3 run.py --model gemini-3-pro-preview-new -s test1223_5 -t ../../dacomp-da/tasks/dacomp-da.jsonl --workers 10 --language en




python3 run.py --model serve_dacomp_da_gemini3_pro_4356_qwen_test2 -s test1224_2 -t ../../dacomp-da/tasks/dacomp-da.jsonl --workers 25 --language en

python3 run.py --model gemini-3-pro-preview-new -s test1224_2 -t ../../dacomp-da/tasks/dacomp-da.jsonl --workers 10 --language en

python3 run.py --model qwen3-coder-30b-a3b -s test1224_2 -t ../../dacomp-da/tasks/dacomp-da.jsonl --workers 10 --language en

python3 run.py --model gemini-2.5-pro -s test1224_2 -t ../../dacomp-da/tasks/dacomp-da.jsonl --workers 10 --language en

python3 run.py --model gemini-2.5-pro -s try1
python3 run.py --model gemini-2.5-pro -s try2
python3 run.py --model gemini-2.5-pro -s try3


python3 run.py --model serve_dacomp_da_gemini3_pro_4356_qwen_test2 -s test1224_3 -t ../../dacomp-da/tasks/dacomp-da.jsonl --workers 25 --language en


python3 run.py --model qwen3-coder-30b-a3b -s test1224_3 -t ../../dacomp-da/tasks/dacomp-da.jsonl --workers 25 --language en



cd /mlx_devbox/users/leifangyu/playground/DAComp-V1/methods/spider-agent-fcmode
python3 run.py --model qwen3-coder-30b-a3b -s test1226_5 -t ../../dacomp-da/tasks/dacomp-da.jsonl --workers 50 --language en
python3 get_results.py qwen3-coder-30b-a3b-test1226_5 --output_dir ../../dacomp-da/evaluation_suite/agent_results
cd ../../dacomp-da/evaluation_suite
python3 llm_judge.py --rubrics-model gemini-2.5-flash --gsb-model-text gemini-2.5-flash --gsb-model-vis gemini-2.5-flash --inputs agent_results/qwen3-coder-30b-a3b-test1226_1 --language en --max-workers 16




cd /mlx_devbox/users/leifangyu/playground/DAComp-V1/methods/spider-agent-fcmode
python3 run.py --model qwen3-coder-30b-a3b -s test1226_7 -t ../../dacomp-da/tasks/dacomp-da.jsonl --workers 25 --language en
python3 get_results.py qwen3-coder-30b-a3b-test1226_7 --output_dir ../../dacomp-da/evaluation_suite/agent_results
cd ../../dacomp-da/evaluation_suite
python3 llm_judge.py --rubrics-model gemini-2.5-flash --gsb-model-text gemini-2.5-flash --gsb-model-vis gemini-2.5-flash --inputs agent_results/qwen3-coder-30b-a3b-test1226_7 --language en --max-workers 16


cd /mlx_devbox/users/leifangyu/playground/DAComp-V1/methods/spider-agent-fcmode
python3 run.py --model doubao-seed-1-6-thinking-dataagent-preview -s test1226_1 -t ../../dacomp-da/tasks/dacomp-da.jsonl --workers 25 --language en
python3 get_results.py doubao-seed-1-6-thinking-dataagent-preview-test1226_1 --output_dir ../../dacomp-da/evaluation_suite/agent_results
cd ../../dacomp-da/evaluation_suite
python3 llm_judge.py --rubrics-model gemini-2.5-flash --gsb-model-text gemini-2.5-flash --gsb-model-vis gemini-2.5-flash --inputs agent_results/doubao-seed-1-6-thinking-dataagent-preview-test1226_1 --language en --max-workers 16

cd /mlx_devbox/users/leifangyu/playground/DAComp-V1/methods/spider-agent-fcmode
python3 run.py --model gemini-3-pro-preview-new -s test1226_1 -t ../../dacomp-da/tasks/dacomp-da.jsonl --workers 25 --language en
python3 get_results.py gemini-3-pro-preview-new-test1226_1 --output_dir ../../dacomp-da/evaluation_suite/agent_results
cd ../../dacomp-da/evaluation_suite
python3 llm_judge.py --rubrics-model gemini-2.5-flash --gsb-model-text gemini-2.5-flash --gsb-model-vis gemini-2.5-flash --inputs agent_results/gemini-3-pro-preview-new-test1226_1 --language en --max-workers 32



cd /mlx_devbox/users/leifangyu/playground/DAComp-V1/methods/spider-agent-fcmode
python3 run.py --model qwen3-coder-30b-a3b -s test1227_1 -t ../../dacomp-da/tasks/dacomp-da.jsonl --workers 50 --language en
python3 get_results.py qwen3-coder-30b-a3b-test1227_1 --output_dir ../../dacomp-da/evaluation_suite/agent_results
cd ../../dacomp-da/evaluation_suite
python3 llm_judge.py --rubrics-model gemini-2.5-flash --gsb-model-text gemini-2.5-flash --gsb-model-vis gemini-2.5-flash --inputs agent_results/qwen3-coder-30b-a3b-test1227_1 --language en --max-workers 32



cd /mlx_devbox/users/leifangyu/playground/DAComp-V1/methods/spider-agent-fcmode
python3 run.py --model qwen3-coder-30b-a3b -s test1227_2 -t ../../dacomp-da/tasks/dacomp-da.jsonl --workers 50 --language en
python3 get_results.py qwen3-coder-30b-a3b-test1227_2 --output_dir ../../dacomp-da/evaluation_suite/agent_results
cd ../../dacomp-da/evaluation_suite
python3 llm_judge.py --rubrics-model gemini-2.5-flash --gsb-model-text gemini-2.5-flash --gsb-model-vis gemini-2.5-flash --inputs agent_results/qwen3-coder-30b-a3b-test1227_2 --language en --max-workers 32



cd /mlx_devbox/users/leifangyu/playground/DAComp-V1/methods/spider-agent-fcmode
python3 run.py --model qwen3-coder-30b-a3b -s test1227_3 -t ../../dacomp-da/tasks/dacomp-da.jsonl --workers 50 --language en
python3 get_results.py qwen3-coder-30b-a3b-test1227_3 --output_dir ../../dacomp-da/evaluation_suite/agent_results
cd ../../dacomp-da/evaluation_suite
python3 llm_judge.py --rubrics-model gemini-2.5-flash --gsb-model-text gemini-2.5-flash --gsb-model-vis gemini-2.5-flash --inputs agent_results/qwen3-coder-30b-a3b-test1227_3 --language en --max-workers 32



cd /mlx_devbox/users/leifangyu/playground/DAComp-V1/methods/spider-agent-fcmode
python3 run.py --model qwen3-coder-30b-a3b -s test1227_4 -t ../../dacomp-da/tasks/dacomp-da.jsonl --workers 50 --language en
python3 get_results.py qwen3-coder-30b-a3b-test1227_4 --output_dir ../../dacomp-da/evaluation_suite/agent_results
cd ../../dacomp-da/evaluation_suite
python3 llm_judge.py --rubrics-model gemini-2.5-flash --gsb-model-text gemini-2.5-flash --gsb-model-vis gemini-2.5-flash --inputs agent_results/qwen3-coder-30b-a3b-test1227_4 --language en --max-workers 32




cd /mlx_devbox/users/leifangyu/playground/DAComp-V1/methods/spider-agent-fcmode
python3 run.py --model qwen3-coder-30b-a3b -s test1227_5 -t ../../dacomp-da/tasks/dacomp-da.jsonl --workers 50 --language en
python3 get_results.py qwen3-coder-30b-a3b-test1227_5 --output_dir ../../dacomp-da/evaluation_suite/agent_results
cd ../../dacomp-da/evaluation_suite
python3 llm_judge.py --rubrics-model gemini-2.5-flash --gsb-model-text gemini-2.5-flash --gsb-model-vis gemini-2.5-flash --inputs agent_results/qwen3-coder-30b-a3b-test1227_5 --language en --max-workers 32









python3 get_results.py qwen3-coder-30b-a3b-test1226_7 --mode f --output_dir ../../dacomp-da/evaluation_suite/agent_results
python3 get_results.py doubao-seed-1-6-thinking-dataagent-preview-test1226_1  --mode f --output_dir ../../dacomp-da/evaluation_suite/agent_results
python3 get_results.py gemini-3-pro-preview-new-test1226_1 --mode f --output_dir ../../dacomp-da/evaluation_suite/agent_results 






python3 run.py --model qwen3-coder-30b-a3b -s test1226_6 -t ../../dacomp-da/tasks/dacomp-da.jsonl --workers 1 --language en



*******

python3 get_results.py serve_dacomp_da_gemini3_pro_4356_qwen_test2-test1224_2 --output_dir ../../dacomp-da/evaluation_suite/agent_results
python3 get_results.py serve_dacomp_da_gemini3_pro_4356_qwen_test2-test1224_3 --output_dir ../../dacomp-da/evaluation_suite/agent_results
python3 get_results.py gemini-3-pro-preview-new-test1224_2 --output_dir ../../dacomp-da/evaluation_suite/agent_results
python3 get_results.py qwen3-coder-30b-a3b-test1224_2 --output_dir ../../dacomp-da/evaluation_suite/agent_results
python3 get_results.py gemini-2.5-pro-test1224_2 --output_dir ../../dacomp-da/evaluation_suite/agent_results

python3 get_results.py qwen3-coder-30b-a3b-test1224_2 --output_dir ../../dacomp-da/evaluation_suite/agent_results
python3 get_results.py gemini-2.5-pro-test1224_2 --output_dir ../../dacomp-da/evaluation_suite/agent_results



*******





Inference 阶段 

问题 -> (LLM Agents) -> 结果/轨迹/答案

Score 阶段

结果/轨迹/答案 -> (某种打分的方法) -> 分数














python3 run.py --model gemini-2.5-pro -s test1230_1 -t ../../dacomp-da/tasks/dacomp-da.jsonl --workers 1 --language en
