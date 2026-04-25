# DV-Sheet

## 1. Download the data

Download the dataset from:

`https://huggingface.co/datasets/DV-World/dvworld`

Place the downloaded files into these folders:

- `../gold`
- `../tasks`

## 2. Install dependencies

Run:

```bash
python3 -m pip install -r requirements.txt
```

## 3. Configure the model

Set up your model in:

`dvworld_agent_fcmode/agent/config.py`

## 4. Run the agent

Use this script:

`run.py`

Example:

```bash
python3 run.py --model kimi-k2-thinking --suffix test1
```

If needed, you can also specify the task file explicitly:

```bash
python3 run.py \
  --model kimi-k2-thinking \
  --suffix test1 \
  --test_path ../tasks/dvsheet-all.jsonl
```

Useful optional flags:

- `--language en` or `--language zh`
- `--type dvsheet-create,dvsheet-fix,dvsheet-dashboards`
- `--workers 1`

The raw outputs will be written to `output/`.

## 5. Convert results for evaluation

Use this script:

`get_results.py`

Example:

```bash
python3 get_results.py kimi-k2-thinking-test1 \
  --output_dir ../evaluation_suite/results
```

It is better to pass `--output_dir` explicitly here, because the current script still contains an old default output path.
