pip-installable django package that gives any django project one reliable payment layer 

****status*** early development (pre-0.1),Not ready for production use

## Why 
Payment integrations tend to fail inthe same ways: forged or replayed callbacks,duplicate prompts ,lost payments ,credit applied twice.LipaHub is extracted from hardened real world billing code built arround the following rules:
    1. A payment cant be lost, double-applied or forged.
    2. Every payment moves through an explicit stste machine.
    3. Webhooks are verified and deduplicated.
    4. Reconciliation jobs resolve anything a webhook missed.
    5. Adding a provider means writing one adapter.

## Planned providers
1. Fake provider for local test
2. Mpesa - daraja use sandbox
3. Airtel Money sandbox
4. Cards use sandbox(s)

## None-current-goals
Payouts, subscriptions, amerchant dashboard,storing card data ,and wallet system

## Development
Requires Docker.
    cp.env.example.env
    docker compose build
    docker compose run --rm lipahub pytest -q

## Roadmap
1. Core:stste machine,models,fake provider,webhook_handling, job
2. Daraja adapter and a sandbox payment end to end
3. Airtel money adapter & more providers
4. Packaging and PyPI release

## License

MIT. see[LICENSE](LICENSE)