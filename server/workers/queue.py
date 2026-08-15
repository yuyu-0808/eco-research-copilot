"""后台任务队列：用 APScheduler 管理调研任务的生命周期（提交 / 状态 / 取消）。

单用户场景下任务数量少，「关闭页面后任务继续跑」的关键是后台线程 + checkpoint
持久化，而非分布式队列，因此用进程内 BackgroundScheduler 即可（不引入 Redis）。
"""

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.executors.pool import ThreadPoolExecutor

_scheduler = None


def get_scheduler() -> BackgroundScheduler:
    """惰性初始化全局调度器（进程内单例，后台线程池跑任务）。"""
    global _scheduler
    if _scheduler is None:
        executors = {"default": ThreadPoolExecutor(max_workers=4)}
        _scheduler = BackgroundScheduler(executors=executors, timezone="Asia/Shanghai")
        _scheduler.start()
    return _scheduler


def submit(project_id: str, func, *args, **kwargs) -> bool:
    """提交一个后台任务。

    - 同一 project_id 已有任务在跑时，直接返回 False（避免重复提交）；
    - 任务完成后 APScheduler 会自动移除 job。
    """
    sched = get_scheduler()
    if sched.get_job(project_id) is not None:
        return False
    sched.add_job(func, args=args, kwargs=kwargs, id=project_id,
                  max_instances=1, coalesce=True)
    return True


def is_running(project_id: str) -> bool:
    """判断某个项目当前是否有任务在后台运行。"""
    return get_scheduler().get_job(project_id) is not None


def cancel(project_id: str) -> bool:
    """移除（取消）某个后台任务；返回是否存在并成功移除。"""
    sched = get_scheduler()
    if sched.get_job(project_id) is not None:
        sched.remove_job(project_id)
        return True
    return False


