---
name: slurm
description: Submit, monitor, and manage SLURM compute jobs on the PVE cluster (ctl + node01). Covers sbatch, srun, squeue, scancel, sacct, and MiQi-specific job templates.
metadata:
  {
    "miqi":
      {
        "emoji": "⚙️",
        "os": ["linux"],
        "notes": "Windows users connect via SSH",
      },
  }
---

# SLURM Skill

Use this skill when the user wants to submit, monitor, cancel, or inspect jobs on the SLURM cluster.

## Cluster & Access

| Host     | Role                         | Access            |
| -------- | ---------------------------- | ----------------- |
| `ctl` | Control node — submit jobs   | `ssh ctl` |

**Windows 用户**: SLURM 命令无法在本地运行，必须先 `ssh ctl`，再在 ctl 上执行。也可 `ssh ctl "squeue"` 直接远程执行。

上传脚本: `scp job.sh ctl:~` | 取回日志: `scp "ctl:~/slurm-%j.out" .`

## Quick Reference

```bash
sinfo                         # cluster/partition status
squeue -u $USER               # my jobs
sbatch job.sh                 # submit
srun --pty bash               # interactive shell
scancel <jobid>               # cancel job
scancel -u $USER              # cancel all my jobs
sacct -j <jobid> --format=JobID,State,Elapsed,MaxRSS
scontrol show job <jobid>     # job details
```

## Windows Quick Reference
```pwsh
ssh ctl "sbatch ~/job.sh" # submit 不要使用转义 按照示例格式输入
ssh ctl "squeue -u $USER"  # my jobs
ssh ctl "scancel <jobid>"  # cancel job
ssh ctl "sacct -j <jobid>" # job details
```
不需要把脚本从 Windows 格式转成 Linux 格式

## 查看任务输出

目前没有nfs共享文件系统，所以不能查看任务输出
