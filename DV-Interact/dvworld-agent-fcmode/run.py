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
    parser.add_argument("--suffix", '-s', type=str, default="interact-0123-gpt-5-mini-2025-08-07")
    
    parser.add_argument("--model", type=str, default="gpt-4.1-2025-04-14")     #  kimi-k2-thinking    Ark-deepseek-v3.2 gemini-2.5-pro  azure-grok-4   glm-4.7  gpt-5.2-2025-12-11    gemini-3-pro-preview-new   openai_qwen3-235b-a22b    openai_qwen3-coder-plus   openai_qwen3-8b
    parser.add_argument("--temperature", type=float, default=0)
    parser.add_argument("--top_p", type=float, default=1.0)
    parser.add_argument("--max_tokens", type=int, default=18192)
    parser.add_argument("--stop_token", type=str, default=None)
    
    # example config
    parser.add_argument("--test_path","-t", type=str, default="/mnt/bn/mjx11/mlx/users/mengjinxiang/repo/DVSheet-1/DV-Interact/tasks/dv-interact.jsonl")
    parser.add_argument("--example_index", "-i", type=str, default="all", help="index range of the examples to run, e.g., '0-10', '2,3', 'all'")
    parser.add_argument("--example_name", "-n", type=str, default="", help="name of the example to run")
    parser.add_argument("--overwriting", action="store_true", default=False)
    parser.add_argument("--retry_failed", action="store_true", default=False)
    
    # output related
    parser.add_argument("--output_dir", type=str, default="output")
    parser.add_argument("--plan", action="store_true")

    parser.add_argument("--dbt_only", action="store_true",default=True)
    parser.add_argument("--image_prompt", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--language", choices=["zh", "en"], default="en", help=argparse.SUPPRESS)

    # user simulator config
    parser.add_argument("--enable_user_simulator", type=lambda x: str(x).lower() == "true", default=True, help="Enable ask_user tool backed by user simulator (default: True). Accepts true/false.")
    parser.add_argument("--user_simulator_model", type=str, default="gpt-5-mini-2025-08-07", help="Model for user simulator (default: agent model)") #o4-mini-2025-04-16  gpt-4.1-2025-04-14  gemini-2.5-flash  gemini-3-flash-preview   gpt-4o-2024-11-20
    parser.add_argument("--user_config_path", type=str, default="/mnt/bn/mjx11/mlx/users/mengjinxiang/repo/DVSheet-1/DV-Interact/user_config/user.json", help="Path to user simulator config (fact_source/table_schema) to merge by instance_id.")
    
    parser.add_argument("--workers", type=int, default=3, help="Number of parallel worker processes")
    parser.add_argument("--worker_id", type=int, default=None, help=argparse.SUPPRESS)
    
    # task type filter: c=creation, e=evolution, d=design
    parser.add_argument("--type", "-k", type=str, default="all", 
                       help="Filter tasks by type: 'c' for creation, 'e' for evolution, 'd' for design, 'ce' for creation+evolution, or 'all' for all types")
    
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

    
    # load user simulator config (by instance_id)
    user_configs = {}
    if args.user_config_path and os.path.exists(args.user_config_path):
        try:
            with open(args.user_config_path, "r") as f:
                loaded = json.load(f)
            if isinstance(loaded, list):
                for item in loaded:
                    iid = item.get("instance_id")
                    if iid:
                        user_configs[iid] = item
        except Exception as exc:
            logger.warning("Failed to load user_config: %s", exc)

    agent = DVWorldAgent(
        model=args.model,
        max_tokens=args.max_tokens,
        top_p=args.top_p,
        temperature=args.temperature,
        max_memory_length=args.max_memory_length,
        max_steps=args.max_steps,
        use_plan=args.plan,
        use_image_prompt=args.image_prompt,
        language=args.language,
        enable_user_simulator=args.enable_user_simulator,
        user_simulator_model=args.user_simulator_model,
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
    
    # Filter by task type if specified
    if args.type != "all":
        task_type_map = {"c": "creation", "e": "evolution", "d": "design"}
        
        # Parse multiple task types (e.g., "ce" means creation + evolution)
        target_types = []
        for char in args.type:
            if char in task_type_map:
                target_types.append(task_type_map[char])
            else:
                logger.error(f"Invalid task type character: '{char}'. Must be 'c', 'e', 'd', or 'all'")
                return
        
        if target_types:
            task_configs = [task for task in task_configs if task.get("type") in target_types]
            logger.info(f"Filtered to {len(task_configs)} tasks of types: {', '.join(target_types)}")
        else:
            logger.error(f"Invalid type parameter: {args.type}. Must be 'c', 'e', 'd', combinations like 'ce', or 'all'")
            return
    
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
    
    # merge user_config into tasks by instance_id
    if user_configs:
        for task in task_configs:
            iid = task.get("instance_id")
            if iid and iid in user_configs:
                task["fact_sheet"] = user_configs[iid]

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
        if os.path.exists(result_json_path):
            if args.overwriting:
                logger.info("Overwriting %s", instance_id)
            else:
                try:
                    with open(result_json_path, "r") as f:
                        result = json.load(f)
                except Exception:
                    result = None
                result_text = result.get("result", "") if isinstance(result, dict) else ""
                result_text_lower = result_text.lower() if isinstance(result_text, str) else ""
                finished = bool(result.get("finished")) if isinstance(result, dict) else False
                success = finished and (not "FAIL" in str(result_text)) and ("error" not in result_text_lower)
                if args.retry_failed:
                    if success:
                        logger.info("Skipping %s", instance_id)
                        continue
                    logger.info("Retrying %s", instance_id)
                else:
                    if finished:
                        logger.info("Skipping %s", instance_id)
                        continue
                    logger.info("Re-running unfinished %s", instance_id)
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
        # Ensure no config.json is present in the mounted workspace at startup.
        try:
            cfg_path = os.path.join(env.mnt_dir, "config.json")
            if os.path.exists(cfg_path):
                os.remove(cfg_path)
                logger.info("Removed config.json from workspace")
        except Exception as exc:
            logger.warning("Failed to remove config.json: %s", exc)
    
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
