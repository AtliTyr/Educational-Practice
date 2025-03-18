import os
from dotenv import load_dotenv
import telebot
import requests
import socket
import json

load_dotenv()
BOT_TOKEN = os.getenv('BOT_TOKEN')

bot = telebot.TeleBot(BOT_TOKEN)

user_sites = {}
user_requests_data = {}


def get_ipv4_address(domain_name):
    try:
        # Получаем список всех IP-адресов для данного домена
        ip_addresses = socket.gethostbyname_ex(domain_name)[2]
        
        # Фильтруем только IPv4 адреса
        ipv4_addresses = [ip for ip in ip_addresses if ':' not in ip]  # Исключаем IPv6 адреса

        if ipv4_addresses:
            return ipv4_addresses
        else:
            return None
    except socket.gaierror:
        return None

def process_request(r):
    status = f"\nStatus code: {r.status_code} \nStatus message: {r.reason} \n"

    if r.headers.get('Set-Cookie'):
        ind_from = r.headers['Set-Cookie'].find('domain=') + 6
        ind_to = r.headers['Set-Cookie'].find(';', ind_from)
        ipv4_addresses = get_ipv4_address(r.headers['Set-Cookie'][ind_from + 1:ind_to].strip('.'))
        
        if ipv4_addresses:
            status += f"IPv4 адрес: {', '.join(ipv4_addresses)}\n"
        else:
            status += f"Не удалось получить IPv4 адрес\n"
    for key in r.headers:
        status += '{}: {}\n'.format(key, r.headers[key])

    return status

####################################################
@bot.message_handler(commands=['help'])
def help_command(message):
    help_text = (
        "/add - добавить сайт в список\n"
        "/list - показать список сайтов\n"
        "/check - проверить состояние сайтов\n"
        "/check <int: index> - проверить состояние сайта\n"
        "/clear - очистить список сайтов\n"
        "/clear <int: index> - удалить сайт из списка\n"
        "/request - сделать HTTP-запрос к сайту\n"
        "/help - показать это сообщение"
    )
    bot.send_message(message.chat.id, help_text)

@bot.message_handler(commands=['start'])
def start(message):
    bot.send_message(message.chat.id, "Привет! Я бот для отслеживания состояния сайтов. Используйте /help для получения информации о моих возможностях.")

@bot.message_handler(commands=['add'])
def add_site(message):
    msg = bot.send_message(message.chat.id, "Введите URL сайта, который хотите добавить:")
    bot.register_next_step_handler(msg, process_site)

def process_site(message):
    site = message.text.strip()
    user_id = message.chat.id

    if user_id not in user_sites:
        user_sites[user_id] = []

    if site in user_sites[user_id]:
        bot.send_message(user_id, f"Сайт {site} уже присутствует в вашем списке")
    else:
        user_sites[user_id].append(site)
        bot.send_message(user_id, f"Сайт {site} добавлен в ваш список.")
####################################################
@bot.message_handler(commands=['clear'])
def clear(message):
    try:
        args = message.text.split()
        if len(args) == 1:
            if len(user_sites[message.chat.id]) != 0:
                user_sites.pop(message.chat.id)
                bot.send_message(message.chat.id, "Ваш список сайтов очищен.")
            else:
                raise KeyError
        elif len(args) > 1:
            sites = user_sites[message.chat.id]
            site = sites[int(args[1]) - 1]
            sites.remove(site)
            bot.send_message(message.chat.id, f"Сайт {site} удалён из списка.")
    except KeyError:
        bot.send_message(message.chat.id, "Вы не добавили ни одного сайта")
    except (TypeError, ValueError, IndexError):
        bot.send_message(message.chat.id, "Проверьте корректность введённого индекса!")

@bot.message_handler(commands=['list'])
def list_sites(message):
    user_id = message.chat.id
    sites = user_sites.get(user_id, [])

    if not sites:
        bot.send_message(user_id, "Ваш список сайтов пуст.")
    else:
        response = "Ваши сайты:\n"
        for index, site in enumerate(sites):
            response += f"{index + 1}. {site}\n"
        bot.send_message(user_id, response)
####################################################
@bot.message_handler(commands=['check'])
def check_sites(message):
    user_id = message.chat.id
    sites = user_sites.get(user_id, [])
    if not sites:
        bot.send_message(user_id, "Ваш список сайтов пуст.")
        return
    args = message.text.split()
    response = " "
    try:
        if len(args) > 1:
            r = requests.get(sites[int(args[1]) - 1], timeout=5)
            status = process_request(r)
            response += f"{args[1]}. {sites[int(args[1]) - 1]} ```{status}```\n"
        else:
            for index, site in enumerate(sites):
                r = requests.get(site, timeout=5)
                status = process_request(r)
                response += f"{index + 1}. {site} ```{status}```\n"
        bot.send_message(user_id, response, parse_mode="markdown")
    except (TypeError, ValueError, IndexError):
        bot.send_message(message.chat.id, "Проверьте корректность введённого индекса!")
        return 
    except requests.exceptions.RequestException:
        status = "не работает (ошибка соединения)"
    except telebot.apihelper.ApiTelegramException:
        bot.send_message(user_id, "Что-то пошло не так")
####################################################
@bot.message_handler(commands=['request'])
def start_req(message):
    msg = bot.send_message(message.chat.id, "Введите URL для HTTP-запроса:")
    bot.register_next_step_handler(msg, get_url)

def get_url(message):
    user_id = message.chat.id
    user_requests_data[user_id] = {'url': message.text}
    bot.send_message(message.chat.id, "Выберите HTTP метод: /get, /post, /put, /delete")
    bot.register_next_step_handler(message, select_method)

def select_method(message):
    method = message.text.lower()
    if method in ['/get', '/post', '/put', '/delete']:
        user_requests_data[message.chat.id]['method'] = method[1:].upper()
        if method in ['/post', '/put']:
            bot.send_message(message.chat.id, "Введите тело запроса (в формате JSON):")
            bot.register_next_step_handler(message, get_body)
        else:
            bot.send_message(message.chat.id, "Введите api_key (\'-\' если не нужен):")
            bot.register_next_step_handler(message, get_api) 
    else:
        bot.send_message(message.chat.id, "Неверный метод. Пожалуйста, выберите /get, /post, /put, /delete.")
        bot.register_next_step_handler(message, select_method)

def get_body(message):
    user_requests_data[message.chat.id]['body'] = message.text
    bot.send_message(message.chat.id, "Введите api_key (\'-\' если не нужен):")
    bot.register_next_step_handler(message, get_api)

def get_api(message):
    if message.text != '-':
        user_requests_data[message.chat.id]['api'] = message.text
    response = make_request(message.chat.id)

    user_requests_data.pop(message.chat.id)

    send_response_file(message.chat.id, response)

def make_request(chat_id):
    url = user_requests_data[chat_id]['url']
    method = user_requests_data[chat_id]['method']
    body = user_requests_data[chat_id].get('body', None)

    try:
        if user_requests_data[chat_id]['api']:
            url += f"?api_key={user_requests_data[chat_id].get('api')}"
    except KeyError:
        pass
    try:
        if method == 'GET':
            response = requests.get(url)
        elif method == 'POST':
            response = requests.post(url, json=json.loads(body))
        elif method == 'PUT':
            response = requests.put(url, json=json.loads(body))
        elif method == 'DELETE':
            response = requests.delete(url)
        else:
            return "Неверный метод."

        return f"Статус код: {response.status_code}\nОтвет: {response.text}"
    except Exception as e:
        return f"Произошла ошибка: {str(e)}"

def send_response_file(chat_id, response):
    # Сохраняем ответ в файл
    file_path = f'{chat_id}.txt'
    with open(file_path, 'w', encoding='utf-8') as file:
        file.write(response)
    
    # Отправляем файл пользователю
    with open(file_path, 'rb') as file:
        bot.send_document(chat_id, file)

    # Удаляем файл после отправки
    os.remove(file_path)

if __name__ == '__main__':
    bot.polling(none_stop=True)
