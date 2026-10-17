---
title: Send emails using msmtp with a Gmail account
author_profile: true
---

## Install msmtp

```sh
sudo apt update
sudo apt install msmtp msmtp-mta ca-certificates
```

---

## Generate a Gmail App Password

1. Log in to your Google Account.
2. Go to Security and enable 2-Step Verification (if not already enabled).
3. Search for App passwords in your account search bar.
4. Create a new app password (e.g., name it "diskha").
5. Copy the 16-character app password.

---

## Configure msmtp

Create a `.msmtprc` file in your home directory. An example is shown below. Be sure to use **your** email address and password in the file.

```sh
# Set default values for all accounts
defaults
auth           on
tls            on
tls_starttls   off
tls_trust_file /etc/ssl/certs/ca-certificates.crt
logfile        ~/.msmtp.log

# Gmail account
account        gmail
host           smtp.gmail.com
port           465
from           your-email@gmail.com
user           your-email@gmail.com
password       your-16-char-app-password

# Set gmail as the default account
account default : gmail
```

### Secure the msmtp configuration file

```sh
chmod 600 ~/.msmtprc
```

## Test

Create a simple email message in a text file (e.g. `/tmp/test-email.txt`):

```sh
Subject: Test email from msmtp

Hello! This email was sent via Gmail using msmtp.
```

Send the test email using `msmtp` and your new `~/.msmtprc` file.

```sh
cat /tmp/test-email.txt | msmtp your-email@gmail.com
```

