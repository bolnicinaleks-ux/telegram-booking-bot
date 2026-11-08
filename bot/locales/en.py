"""Английский перевод интерфейса (BOT_LANG=en). Ключ — русский текст из кода."""

EN = {
    # Меню и кнопки
    "📅 Записаться": "📅 Book",
    "📋 Мои записи": "📋 My bookings",
    "◀️ Назад": "◀️ Back",
    "✖️ Отмена": "✖️ Cancel",
    "✅ Подтвердить": "✅ Confirm",
    "Ваше имя": "Your name",
    "📱 Отправить мой номер": "📱 Share my phone number",
    "Да, отменить": "Yes, cancel",
    "Нет": "No",
    "❌ Отменить запись": "❌ Cancel booking",
    "❌ Отменить #{id} · {day} {time}": "❌ Cancel #{id} · {day} {time}",
    "{name} · {duration} мин · {price}": "{name} · {duration} min · {price}",
    "Записаться": "Book an appointment",
    "Мои записи": "My bookings",
    "Главное меню": "Main menu",

    # Услуги по умолчанию
    "Стрижка": "Haircut",
    "Окрашивание": "Hair coloring",
    "Консультация": "Consultation",

    # Клиент
    "\n\n🧪 <b>Это демо-бот.</b> После записи вы получите копию карточки, "
    "которую видит владелец, и сможете сами отменить запись как администратор.":
        "\n\n🧪 <b>This is a demo bot.</b> After booking you'll get a copy of the card the owner sees, "
        "and you can cancel the booking yourself as the admin.",
    "Здравствуйте! Здесь можно записаться на приём.\n\n{book} — новая запись\n{my} — ваши записи":
        "Hello! You can book an appointment here.\n\n{book} — new booking\n{my} — your bookings",
    "Услуга: <b>{name}</b> · {duration} мин · {price}": "Service: <b>{name}</b> · {duration} min · {price}",
    "Когда: <b>{when}</b>": "When: <b>{when}</b>",
    "Имя: {name}": "Name: {name}",
    "Телефон: {phone}": "Phone: {phone}",
    "Выберите услугу:": "Choose a service:",
    "Сейчас нет доступных услуг.": "No services are available right now.",
    "Выберите дату:": "Choose a date:",
    "Свободных дат нет. Выберите другую услугу.": "No free dates. Please choose another service.",
    "Дата: <b>{day}</b>\n\nВыберите время:": "Date: <b>{day}</b>\n\nChoose a time:",
    "У вас нет предстоящих записей.": "You have no upcoming bookings.",
    "<b>Ваши записи</b>": "<b>Your bookings</b>",
    "У вас уже {n} активных записей. Отмените одну из них в разделе «{my}».":
        "You already have {n} active bookings. Cancel one of them in “{my}”.",
    "Услуга недоступна": "This service is unavailable",
    "На эту дату свободного времени уже нет": "There are no free slots left on this date",
    "Это время уже занято, выберите другое": "This time is already taken, please choose another",
    "Как к вам обращаться? Напишите имя.": "What's your name?",
    "Имя должно быть от 2 до 50 символов.": "The name must be 2 to 50 characters long.",
    "Ваш номер телефона — кнопкой ниже или текстом:": "Your phone number — use the button below or type it:",
    "Не похоже на номер телефона. Пример: +7 701 123 45 67":
        "That doesn't look like a phone number. Example: +1 555 123 4567",
    "Проверьте данные 👇": "Please check the details 👇",
    "Отправьте ответ текстом.": "Please reply with text.",
    "Достигнут лимит активных записей ({n}).": "You've reached the limit of active bookings ({n}).",
    "Это время уже недоступно, выберите другое": "This time is no longer available, please choose another",
    "Это время только что заняли, выберите другое": "Someone just took this time, please choose another",
    "✅ <b>Вы записаны!</b> Номер записи #{id}": "✅ <b>You're booked!</b> Booking #{id}",
    "🆕 <b>Новая запись</b>": "🆕 <b>New booking</b>",
    "👀 <b>Так эту запись увидит владелец</b> — кнопка работает:":
        "👀 <b>This is what the owner sees</b> — the button works:",
    "Запись отменена.": "Booking cancelled.",
    "Запись не найдена или уже неактуальна": "Booking not found or no longer valid",
    "Отменить запись?": "Cancel this booking?",
    "Запись не найдена или уже отменена": "Booking not found or already cancelled",
    "Запись #{id} отменена.": "Booking #{id} has been cancelled.",
    "❌ <b>Клиент отменил запись</b>": "❌ <b>The client cancelled a booking</b>",
    "Кнопка устарела. Начните заново: /book": "This button is outdated. Start again: /book",
    "⏰ Напоминание: {when} — {service}.\nЕсли не сможете прийти, отмените запись в «{my}».":
        "⏰ Reminder: {when} — {service}.\nIf you can't make it, please cancel in “{my}”.",

    # Админ
    "<b>Админ-панель</b>\n\n"
    "/today — записи на сегодня\n"
    "/tomorrow — записи на завтра\n"
    "/day ДД.ММ[.ГГГГ] — записи на дату\n"
    "/services — список услуг\n"
    "/addservice Название | минуты | цена — добавить услугу\n"
    "/delservice ID — скрыть услугу":
        "<b>Admin panel</b>\n\n"
        "/today — today's bookings\n"
        "/tomorrow — tomorrow's bookings\n"
        "/day DD.MM[.YYYY] — bookings for a date\n"
        "/services — list of services\n"
        "/addservice Name | minutes | price — add a service\n"
        "/delservice ID — hide a service",
    "Записей нет.": "No bookings.",
    " · записей: {n}": " · bookings: {n}",
    "Формат: /day 05.11 или /day 05.11.2026": "Format: /day 05.11 or /day 05.11.2026 (day.month)",
    "Услуг нет. Добавьте: /addservice Название | 60 | 5000": "No services yet. Add one: /addservice Name | 60 | 50",
    "<b>Услуги</b>": "<b>Services</b>",
    "Формат: /addservice Название | минуты | цена\n"
    "Пример: /addservice Маникюр | 90 | 7000\n"
    "Длительность 5–600 мин, цена ≥ 0.":
        "Format: /addservice Name | minutes | price\n"
        "Example: /addservice Manicure | 90 | 40\n"
        "Duration 5–600 min, price ≥ 0.",
    "Добавлено: <code>{id}</code> · {name} · {duration} мин · {price}":
        "Added: <code>{id}</code> · {name} · {duration} min · {price}",
    "Формат: /delservice ID (ID — в /services)": "Format: /delservice ID (see IDs in /services)",
    "Услуга {id} скрыта. Существующие записи сохранены.": "Service {id} is hidden. Existing bookings are kept.",
    "Услуга не найдена или уже скрыта.": "Service not found or already hidden.",
    "Нет доступа": "Access denied",
    "Запись уже отменена": "This booking is already cancelled",
    "Ваша запись отменена администратором:": "Your booking was cancelled by the administrator:",
    "⚠️ Клиент не получил уведомление (бот заблокирован).": "⚠️ The client didn't get the notification (bot is blocked).",
    "🧪 Демо: клиент отменил запись через карточку владельца":
        "🧪 Demo: a client cancelled a booking via the owner's card",
    "Запись #{id} оставлена.": "Booking #{id} kept.",

    # Даты
    "Пн": "Mon", "Вт": "Tue", "Ср": "Wed", "Чт": "Thu", "Пт": "Fri", "Сб": "Sat", "Вс": "Sun",
    "января": "January", "февраля": "February", "марта": "March", "апреля": "April",
    "мая": "May", "июня": "June", "июля": "July", "августа": "August",
    "сентября": "September", "октября": "October", "ноября": "November", "декабря": "December",
}
