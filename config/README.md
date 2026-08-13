# Runtime configuration

The executable uses conservative built-in paper defaults when no local configuration file is present.

To override research parameters locally, create `config/trading_params.yaml`. Keep machine-specific paths and any future credentials out of version control. The typed loader validates storage, analytics, strategy, and risk sections before the event loop starts.
