# Установка systemd сервисов

## Установка

```bash
sudo cp etc/systemd/*.service /etc/systemd/system/
sudo cp etc/systemd/*.timer /etc/systemd/system/

sudo systemctl daemon-reload

sudo systemctl enable --now amocrm-ping-probe.timer
sudo systemctl enable --now amocrm-daily-report.timer
```

## Проверка статуса

```bash
systemctl list-timers
systemctl status amocrm-ping-probe.timer
systemctl status amocrm-daily-report.timer

journalctl -u amocrm-ping-probe.service -f
journalctl -u amocrm-daily-report.service -f
```

## Ручной запуск

```bash
sudo systemctl start amocrm-ping-probe.service
sudo systemctl start amocrm-daily-report.service
```

## Расписание

- **amocrm-ping-probe**: каждый час
- **amocrm-daily-report**: каждый день в 03:00
