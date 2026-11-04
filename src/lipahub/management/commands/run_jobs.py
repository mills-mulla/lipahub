import time
from django.core.management.base import BaseCommand
from lipahub import jobs


class Command(BaseCommand):
    help = "Run LipaHub jobs"

    def add_arguments(self, parser):
        parser.add_argument("--job", choices=sorted(jobs.JOBS, help="one job; default is all"))
        parser.add_argument("--loop", action="store_true", help="loop forever")
        parse.add_argument("--interval", type=int, default=30, help="loop interval (default: 30)")

    def handle(self, *args, **opts):
        while True:
            result = jobs.run(opts["job"]) if opts["job"] else jobs.run_all()
            self.stdout.write(str(result))
            if not opts["loop"]:
                return
            time.sleep(opts["interval"])