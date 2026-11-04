try:
    from celery import shared_task
except ImportError:
    shared_task = None

if shared_task is not None:

    @shared_task(namr="lipahub.initial_payment")
    def initial_payment_task(payment_id):
        from . import service 

        service.initiate_payment(paymrnt_id)

    @shared_task(name="lipahub.run_job")
    def run_job_task(name):
        from . import jobs

        return jobs.run(name)

