import argparse
import datetime
import json
import logging
import os
import random
import sys
import subprocess
import glob

from tqdm import tqdm

from dvworld_agent_fcmode.envs.spider_agent import Spider_Agent_Env
from dvworld_agent_fcmode.agent.agents import DVWorldAgent


#  Logger Configs {{{ #
logger = logging.getLogger("dvworld_agent_fcmode")
logger.setLevel(logging.DEBUG)

datetime_str: str = datetime.datetime.now().strftime("%Y%m%d@%H%M%S")

file_handler = logging.FileHandler(os.path.join("logs", "normal-{:}.log".format(datetime_str)), encoding="utf-8")
debug_handler = logging.FileHandler(os.path.join("logs", "debug-{:}.log".format(datetime_str)), encoding="utf-8")
stdout_handler = logging.StreamHandler(sys.stdout)
sdebug_handler = logging.FileHandler(os.path.join("logs", "sdebug-{:}.log".format(datetime_str)), encoding="utf-8")

file_handler.setLevel(logging.INFO)
debug_handler.setLevel(logging.DEBUG)
stdout_handler.setLevel(logging.INFO)
sdebug_handler.setLevel(logging.DEBUG)

formatter = logging.Formatter(
    fmt="\x1b[1;33m[%(asctime)s \x1b[31m%(levelname)s \x1b[32m%(module)s/%(lineno)d-%(processName)s\x1b[1;33m] \x1b[0m%(message)s")
file_handler.setFormatter(formatter)
debug_handler.setFormatter(formatter)
stdout_handler.setFormatter(formatter)
sdebug_handler.setFormatter(formatter)

stdout_handler.addFilter(logging.Filter("dvworld_agent_fcmode"))
sdebug_handler.addFilter(logging.Filter("dvworld_agent_fcmode"))

logger.addHandler(file_handler)
logger.addHandler(debug_handler)
logger.addHandler(stdout_handler)
logger.addHandler(sdebug_handler)
#  }}} Logger Configs # 



def config() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run end-to-end evaluation on the benchmark"
    )
    
    parser.add_argument("--max_steps", type=int, default=60)
    
    parser.add_argument("--max_memory_length", type=int, default=120)
    parser.add_argument("--suffix", '-s', type=str, default="all-0123")
    
    parser.add_argument("--model", type=str, default="kimi-k2-thinking")    # openai_qwen3-coder-plus  glm-4.7 gemini-2.5-pro   gpt-4.1-2025-04-14   azure-grok-4    kimi-k2-thinking gpt-5.2-2025-12-11  gemini-3-pro-preview-new  openai_qwen3-235b-a22b   openai_qwen3-8b  Ark-deepseek-v3.2
    parser.add_argument("--temperature", type=float, default=0)
    parser.add_argument("--top_p", type=float, default=1.0)
    parser.add_argument("--max_tokens", type=int, default=18192)
    parser.add_argument("--stop_token", type=str, default=None)
    
    # example config
    parser.add_argument("--test_path","-t", type=str, default="../tasks/dvsheet-all.jsonl")
    parser.add_argument("--example_index", "-i", type=str, default="all", help="index range of the examples to run, e.g., '0-10', '2,3', 'all'")
    parser.add_argument("--example_name", "-n", type=str, default="", help="name of the example to run")
    parser.add_argument("--overwriting", action="store_true", default=False)
    parser.add_argument("--retry_failed", action="store_true", default=False)

    # output related
    parser.add_argument("--output_dir", type=str, default="output")
    parser.add_argument("--plan", action="store_true")

    parser.add_argument("--dbt_only", action="store_true",default=True)
    parser.add_argument("--language", choices=["zh", "en"], default="en", help=argparse.SUPPRESS)
    
    parser.add_argument("--workers", type=int, default=5, help="Number of parallel worker processes")
    parser.add_argument("--worker_id", type=int, default=None, help=argparse.SUPPRESS)
    # seed prompts not supported
    
    # task type filter by instance_id prefix
    parser.add_argument("--type", "-k", type=str, default="all", 
                       help="Filter tasks by prefix (e.g., 'dvsheet-create', 'dvsheet-fix', 'dvsheet-dashboards') or 'all'. Comma-separated allowed.")
    
    args = parser.parse_args()

    return args


def _launch_worker_processes(args: argparse.Namespace) -> None:
    script_path = os.path.abspath(__file__)
    base_argv = sys.argv[1:]
    processes = []
    logger.info("Spawning %d worker processes", args.workers)
    for worker_idx in range(args.workers):
        worker_cmd = [
            sys.executable,
            script_path,
            *base_argv,
            "--worker_id",
            str(worker_idx),
        ]
        proc = subprocess.Popen(worker_cmd)
        processes.append((worker_idx, proc))
    errors = []
    for worker_idx, proc in processes:
        code = proc.wait()
        if code != 0:
            errors.append((worker_idx, code))
    if errors:
        raise RuntimeError(
            "Workers failed: " + ", ".join(f"id={idx} code={code}" for idx, code in errors)
        )


def _select_tasks_for_worker(task_configs, args: argparse.Namespace):
    if args.worker_id is None or args.workers <= 1:
        return task_configs
    selected = [
        task for idx, task in enumerate(task_configs) if idx % args.workers == args.worker_id
    ]
    logger.info(
        "Worker %s/%s handling %d tasks",
        args.worker_id,
        args.workers,
        len(selected),
    )
    return selected



def test(
    args: argparse.Namespace,
    test_all_meta: dict = None
) -> None:
    scores = []
    
    # log args
    logger.info("Args: %s", args)

    if args.suffix == "":
        logger.warning("No suffix is provided, the experiment id will be the model name.")
        experiment_id = args.model.split("/")[-1]
    else:
        experiment_id = args.model.split("/")[-1] + "-" + args.suffix
        
    if args.plan:
        experiment_id = f"{experiment_id}-plan"

    
    agent = DVWorldAgent(
        model=args.model,
        max_tokens=args.max_tokens,
        top_p=args.top_p,
        temperature=args.temperature,
        max_memory_length=args.max_memory_length,
        max_steps=args.max_steps,
        use_plan=args.plan,
        use_image_prompt=False,
        language=args.language,
    )
    valid_ids = []
    ## load task configs (support jsonl and json)
    assert os.path.exists(args.test_path), f"Invalid test_path, must be an existing file: {args.test_path}"
    task_configs = []
    if args.test_path.endswith(".jsonl"):
        with open(args.test_path, "r") as f:
            task_configs = [json.loads(line) for line in f]
    elif args.test_path.endswith(".json"):
        with open(args.test_path, "r") as f:
            data = json.load(f)
        if isinstance(data, list):
            task_configs = data
        elif isinstance(data, dict):
            task_configs = [data]
        else:
            raise ValueError("Invalid json task format: expected list or dict.")
    else:
        raise ValueError("Invalid test_path extension, expected .jsonl or .json.")
    
    # Filter by prefix if specified
    if args.type != "all":
        prefixes = [p.strip() for p in args.type.split(",") if p.strip()]
        task_configs = [task for task in task_configs if any(task.get("instance_id", "").startswith(pref) for pref in prefixes)]
        logger.info(f"Filtered to {len(task_configs)} tasks with prefixes: {', '.join(prefixes)}")
    
    if args.example_name != "":
        task_configs = [task for task in task_configs if args.example_name in task["id"]]
    else:
        if args.example_index != "all":
            if "-" in args.example_index:
                start, end = map(int, args.example_index.split("-"))
                task_configs = task_configs[start:end]
            else:
                indices = list(map(int, args.example_index.split(",")))
                task_configs = [task_configs[i] for i in indices]
    
    task_configs = _select_tasks_for_worker(task_configs, args)
    if not task_configs:
        logger.info("No tasks assigned to this worker. Exiting.")
        return

    for task_config in task_configs:
        instance_id = experiment_id +"/"+ task_config["instance_id"]
        output_dir = os.path.join(args.output_dir, instance_id)
        result_json_path =os.path.join(output_dir, "dvworld/result.json")

        
      
        task_type = None
        if task_config["instance_id"].startswith("bq") or task_config["instance_id"].startswith("ga"):
            task_type = 'bq'
        elif task_config["instance_id"].startswith("local"):
            task_type = 'local'
        elif task_config["instance_id"].startswith("sf"):
            task_type = 'sf'
        elif task_config["instance_id"].startswith("ch0"):
            task_type = 'ch'
        elif task_config["instance_id"].startswith("postgres"):
            task_type = 'pg'
        else:
            task_type = 'dbt'


        valid_types = set()

        if args.dbt_only: valid_types.add('dbt')



        valid_ids.append(task_config["instance_id"])
        
        
        result = None
        if os.path.exists(result_json_path) and not args.overwriting:
            logger.info("Skipping %s (result exists)", instance_id)
            continue
        elif os.path.exists(result_json_path) and args.overwriting:
            logger.info("Overwriting %s", instance_id)
        else:
            logger.info("Running %s", instance_id)
            
        if os.path.exists(output_dir):
            os.system(f"rm -rf {output_dir}")
            logger.info("Removed existing %s", output_dir)

        os.makedirs(output_dir, exist_ok=True)


        source_data_dir = os.path.dirname(args.test_path)

        env_config = \
        {
            "init_args": {
                "name": experiment_id,
                "work_dir": "/workspace",
                "language": args.language,
            }
        }

        task_config['config'] = [{"type": "copy_all_subfiles", "parameters": {"dirs": [os.path.join(source_data_dir, task_config["instance_id"])]}}]


        env_config["init_args"]["name"] = experiment_id +"-"+ task_config["instance_id"]

          


        env = Spider_Agent_Env(
            env_config=env_config,
            task_config=task_config,
            cache_dir="./cache",
            mnt_dir=output_dir
        )
    
        agent.set_env_and_task(env)
    
        logger.info('Task input:' + task_config['instruction'])
        done, result_output = agent.run()
        trajectory = agent.get_trajectory()

        os.makedirs(os.path.join(output_dir, "dvworld"), exist_ok=True)
        result_files = env.post_process()
        dvworld_result = {"finished": done, "steps": len(trajectory["trajectory"]),
                           "result": result_output,"result_files": result_files, **trajectory}
        with open(os.path.join(output_dir, "dvworld/result.json"), "w", encoding='utf-8') as f:
            json.dump(dvworld_result, f, indent=2, ensure_ascii=False)
        

        logger.info("Finished %s", instance_id)
        env.close()




if __name__ == '__main__':
    cli_args = config()
    if cli_args.workers > 1 and cli_args.worker_id is None:
        _launch_worker_processes(cli_args)
    else:
        if cli_args.worker_id is not None:
            if cli_args.worker_id < 0 or cli_args.worker_id >= cli_args.workers:
                raise ValueError(
                    f"worker_id must be within [0, {cli_args.workers - 1}] when provided."
                )
            logger.info("Starting worker %s/%s", cli_args.worker_id, cli_args.workers)
        test(cli_args)
