# Security

This project is designed to run locally. It handles OpenAI API keys and email SMTP app passwords, so do not deploy it publicly unless you first redesign the credential flow.

Never commit these files or values:

- `.env`
- OpenAI API keys
- SMTP app passwords or email authorization codes
- Personal sender or receiver email addresses

For GitHub, commit `.env.example` only. Users should copy it to `.env` on their own machine and fill in their own values.
