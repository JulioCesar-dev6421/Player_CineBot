import os
import logging
import httpx
import asyncio
import re
from typing import Dict, List, Optional, Any, Tuple
from telegram import (
    Update, 
    InlineKeyboardButton, 
    InlineKeyboardMarkup, 
    ReplyKeyboardMarkup
)
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ContextTypes,
)

# Configuração de Logs
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# ==========================================
# CONFIGURAÇÕES E CHAVES
# ==========================================
TELEGRAM_TOKEN = "8938993465:AAFWgL9Gy4SEVW_K6yCmUqzw3ylyC1VsB04"
TMDB_API_KEY = "22912078ff35f60b25b594d01f58c1d0"

# URL Base para renderização do Player CineBot
PLAYER_BASE_URL = "https://juliocesar-dev6421.github.io/Player_CineBot/"

# ==========================================
# FUNÇÕES DE FEEDBACK VISUAL
# ==========================================

async def manter_digitando(chat_id: int, context: ContextTypes.DEFAULT_TYPE, stop_event: asyncio.Event):
    """Envia o status de 'digitando' continuamente enquanto busca os dados."""
    while not stop_event.is_set():
        try:
            await context.bot.send_chat_action(chat_id=chat_id, action="typing")
        except Exception as e:
            logger.error(f"Erro ao enviar status de digitando: {e}")
        await asyncio.sleep(4)

# ==========================================
# BUSCA E TRATAMENTO DE DADOS DO TMDB (ASSÍNCRONO)
# ==========================================

async def buscar_conteudo_tmdb(query: str) -> Optional[Dict[str, Any]]:
    """
    Busca um filme ou série no TMDb e retorna os dados estruturados do melhor resultado.
    """
    url = "https://api.themoviedb.org/3/search/multi"
    params = {
        "api_key": TMDB_API_KEY,
        "query": query,
        "language": "pt-BR",
        "include_adult": "false"
    }
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url, params=params, timeout=15.0)
            if response.status_code != 200:
                return None
                
            data = response.json()
            results = data.get("results", [])
            
            if not results:
                return None
            
            # Filtra para obter apenas itens que sejam 'movie' ou 'tv'
            resultados_validos = [r for r in results if r.get("media_type") in ["movie", "tv"]]
            
            if not resultados_validos:
                return None
                
            # Seleciona o primeiro resultado (mais relevante)
            best_match = resultados_validos[0]
            media_type = best_match.get("media_type")
            
            tipo_player = "filme" if media_type == "movie" else "serie"
            id_conteudo = best_match.get("id")
            title = best_match.get("title") or best_match.get("name") or "Sem título"
            overview = best_match.get("overview") or "Sinopse não disponível em português."
            rating = best_match.get("vote_average", 0.0)
            release_date = best_match.get("release_date") or best_match.get("first_air_date") or "N/A"
            
            poster_path = best_match.get("poster_path")
            poster_url = f"https://image.tmdb.org/t/p/w500{poster_path}" if poster_path else None
            
            return {
                "id": id_conteudo,
                "tipo": tipo_player,
                "titulo": title,
                "sinopse": overview,
                "nota": rating,
                "lancamento": release_date,
                "poster": poster_url,
                "media_type": media_type
            }
            
    except Exception as e:
        logger.error(f"Erro ao buscar no TMDb: {e}")
        return None

async def obter_detalhes_por_id(id_conteudo: int, tipo: str) -> Optional[Dict[str, Any]]:
    """Busca detalhes de um filme ou série usando diretamente o ID do TMDb."""
    media_type = "movie" if tipo == "filme" else "tv"
    url = f"https://api.themoviedb.org/3/{media_type}/{id_conteudo}"
    params = {
        "api_key": TMDB_API_KEY,
        "language": "pt-BR"
    }
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url, params=params, timeout=15.0)
            if response.status_code != 200:
                return None
                
            data = response.json()
            title = data.get("title") or data.get("name") or "Sem título"
            overview = data.get("overview") or "Sinopse não disponível em português."
            rating = data.get("vote_average", 0.0)
            release_date = data.get("release_date") or data.get("first_air_date") or "N/A"
            poster_path = data.get("poster_path")
            poster_url = f"https://image.tmdb.org/t/p/w500{poster_path}" if poster_path else None
            
            return {
                "id": id_conteudo,
                "tipo": tipo,
                "titulo": title,
                "sinopse": overview,
                "nota": rating,
                "lancamento": release_date,
                "poster": poster_url
            }
    except Exception as e:
        logger.error(f"Erro ao buscar detalhes por ID: {e}")
        return None

async def obter_tendencias_tmdb(tipo_midia: str = "all") -> List[Dict[str, Any]]:
    """Busca as tendências da semana no TMDb (all, movie, tv)."""
    url = f"https://api.themoviedb.org/3/trending/{tipo_midia}/week"
    params = {
        "api_key": TMDB_API_KEY,
        "language": "pt-BR"
    }
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url, params=params, timeout=15.0)
            data = response.json()
            return data.get("results", [])[:5]
    except Exception as e:
        logger.error(f"Erro ao buscar tendências: {e}")
        return []

async def obter_recomendacoes_tmdb(id_conteudo: int, tipo: str) -> List[Dict[str, Any]]:
    """Busca recomendações semelhantes baseadas em um ID do TMDb."""
    media_type = "movie" if tipo == "filme" else "tv"
    url = f"https://api.themoviedb.org/3/{media_type}/{id_conteudo}/recommendations"
    params = {
        "api_key": TMDB_API_KEY,
        "language": "pt-BR"
    }
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url, params=params, timeout=15.0)
            data = response.json()
            return data.get("results", [])[:3]
    except Exception as e:
        logger.error(f"Erro ao buscar recomendações: {e}")
        return []

def xml_clean(html_text: str) -> str:
    """Helper simples para limpar tags HTML básicas de strings."""
    clean = re.compile('<.*?>')
    return re.sub(clean, '', html_text)

# ==========================================
# HANDLERS DO TELEGRAM
# ==========================================

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler para o comando /start."""
    keyboard = [
        ["🎬 Buscar Filme ou Série"],
        ["🔥 Filmes em Alta", "📺 Séries em Alta"]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    
    welcome_text = (
        "🎬 *Bem-vindo ao CineBot!* 🍿\n\n"
        "Seu portal definitivo de entretenimento! Comigo você busca qualquer título, recebe recomendações "
        "personalizadas de conteúdos parecidos com capas completas e assiste a tudo diretamente pelo nosso player!\n\n"
        "📌 *Como começar:*\n"
        "Apenas digite o nome de qualquer filme ou série que queira encontrar! Ou use os botões rápidos do menu abaixo."
    )
    await update.message.reply_text(welcome_text, parse_mode="Markdown", reply_markup=reply_markup)

async def cmd_ajuda(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler para o comando /ajuda."""
    ajuda_text = (
        "💡 *Como aproveitar o CineBot ao máximo:*\n\n"
        "• *Pesquisa direta:* Digite o nome de qualquer filme ou série no chat a qualquer hora.\n"
        "• *Recomendações:* Ao ver os detalhes de um filme, clique em '✨ Recomendados' para ver títulos similares com seus pôsters de capa.\n"
        "• *Player:* Clique em '🍿 Assistir' para rodar o player de vídeo integrado.\n"
        "• *Menu:* Use o teclado fixo na sua barra de digitação para navegar nas tendências."
    )
    await update.message.reply_text(ajuda_text, parse_mode="Markdown")

async def apresentar_tendencias(update: Update, context: ContextTypes.DEFAULT_TYPE, tipo_midia: str):
    """Mostra as tendências de filmes ou séries acompanhadas de seus respectivos pôsters de capa."""
    chat_id = update.effective_chat.id
    stop_typing_event = asyncio.Event()
    typing_task = asyncio.create_task(manter_digitando(chat_id, context, stop_typing_event))
    
    label = "Filmes" if tipo_midia == "movie" else "Séries de TV"
    
    try:
        trends = await obter_tendencias_tmdb(tipo_midia)
        if not trends:
            await update.message.reply_text("Desculpe, não consegui carregar as tendências agora. 😢")
            return
            
        await update.message.reply_text(f"🔥 *As {label} mais assistidas desta semana:*")
        
        for item in trends:
            title = item.get("title") or item.get("name") or "Sem título"
            id_conteudo = item.get("id")
            tipo_player = "filme" if tipo_midia == "movie" else "serie"
            rating = item.get("vote_average", 0.0)
            release_date = item.get("release_date") or item.get("first_air_date") or "N/A"
            overview = item.get("overview") or "Sinopse não disponível em português."
            
            poster_path = item.get("poster_path")
            poster_url = f"https://image.tmdb.org/t/p/w500{poster_path}" if poster_path else None
            
            url_player = f"{PLAYER_BASE_URL}?tipo={tipo_player}&id={id_conteudo}"
            
            keyboard = [
                [
                    InlineKeyboardButton("🍿 Assistir", url=url_player),
                    InlineKeyboardButton("✨ Recomendados", callback_data=f"recomendar:{tipo_player}:{id_conteudo}")
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            detalhes_texto = (
                f"🎬 *{title}*\n"
                f"📅 *Lançamento:* {release_date}\n"
                f"⭐ *Nota:* {rating:.1f}/10\n\n"
                f"📝 *Sinopse:*\n{overview[:300]}..."
            )
            
            if poster_url:
                try:
                    await context.bot.send_photo(
                        chat_id=chat_id,
                        photo=poster_url,
                        caption=detalhes_texto[:1024],
                        parse_mode="Markdown",
                        reply_markup=reply_markup
                    )
                except Exception as e:
                    logger.error(f"Erro ao enviar pôster da tendência: {e}")
                    await update.message.reply_text(
                        detalhes_texto,
                        parse_mode="Markdown",
                        reply_markup=reply_markup
                    )
            else:
                await update.message.reply_text(
                    detalhes_texto,
                    parse_mode="Markdown",
                    reply_markup=reply_markup
                )
    finally:
        stop_typing_event.set()
        await typing_task

async def handle_callback_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Trata cliques em botões inline de forma dinâmica, trazendo posters e botões."""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    chat_id = query.message.chat.id
    
    stop_typing_event = asyncio.Event()
    typing_task = asyncio.create_task(manter_digitando(chat_id, context, stop_typing_event))
    
    try:
        # Se o botão clicado for para ver mais Detalhes de um título
        if data.startswith("detalhes:"):
            _, tipo, id_conteudo = data.split(":")
            id_conteudo = int(id_conteudo)
            
            conteudo = await obter_detalhes_por_id(id_conteudo, tipo)
            if conteudo:
                url_player = f"{PLAYER_BASE_URL}?tipo={conteudo['tipo']}&id={conteudo['id']}"
                
                keyboard = [
                    [
                        InlineKeyboardButton("🍿 Assistir", url=url_player),
                        InlineKeyboardButton("✨ Recomendados", callback_data=f"recomendar:{conteudo['tipo']}:{conteudo['id']}")
                    ]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                nota_formatada = f"{conteudo['nota']:.1f}"
                detalhes_texto = (
                    f"🎬 *{conteudo['titulo']}*\n"
                    f"📅 *Lançamento:* {conteudo['lancamento']}\n"
                    f"⭐ *Nota:* {nota_formatada}/10\n\n"
                    f"📝 *Sinopse:*\n{conteudo['sinopse']}"
                )
                
                if conteudo["poster"]:
                    await context.bot.send_photo(
                        chat_id=chat_id,
                        photo=conteudo["poster"],
                        caption=detalhes_texto[:1024],
                        parse_mode="Markdown",
                        reply_markup=reply_markup
                    )
                else:
                    await context.bot.send_message(
                        chat_id=chat_id,
                        text=detalhes_texto,
                        parse_mode="Markdown",
                        reply_markup=reply_markup
                    )
                    
        # Se o botão clicado for para buscar Recomendações semelhantes (com posters)
        elif data.startswith("recomendar:"):
            _, tipo, id_conteudo = data.split(":")
            id_conteudo = int(id_conteudo)
            
            recomendações = await obter_recomendacoes_tmdb(id_conteudo, tipo)
            if not recomendações:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text="Não encontrei títulos parecidos para recomendar no momento. 😢"
                )
                return
                
            await context.bot.send_message(
                chat_id=chat_id,
                text="🍿 *Se você gostou desse, com certeza vai adorar assistir estes:* \n"
            )
            
            for item in recomendações:
                title = item.get("title") or item.get("name") or "Sem título"
                item_id = item.get("id")
                rating = item.get("vote_average", 0.0)
                release_date = item.get("release_date") or item.get("first_air_date") or "N/A"
                overview = item.get("overview") or "Sinopse não disponível em português."
                
                poster_path = item.get("poster_path")
                poster_url = f"https://image.tmdb.org/t/p/w500{poster_path}" if poster_path else None
                
                url_player = f"{PLAYER_BASE_URL}?tipo={tipo}&id={item_id}"
                
                keyboard = [
                    [
                        InlineKeyboardButton("🍿 Assistir", url=url_player),
                        InlineKeyboardButton("✨ Detalhes", callback_data=f"detalhes:{tipo}:{item_id}")
                    ]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                detalhes_texto = (
                    f"📌 *{title}*\n"
                    f"📅 *Lançamento:* {release_date}\n"
                    f"⭐ *Nota:* {rating:.1f}/10\n\n"
                    f"📝 *Sinopse:*\n{overview[:300]}..."
                )
                
                if poster_url:
                    try:
                        await context.bot.send_photo(
                            chat_id=chat_id,
                            photo=poster_url,
                            caption=detalhes_texto[:1024],
                            parse_mode="Markdown",
                            reply_markup=reply_markup
                        )
                    except Exception as e:
                        logger.error(f"Erro ao enviar pôster recomendado: {e}")
                        await context.bot.send_message(
                            chat_id=chat_id,
                            text=detalhes_texto,
                            parse_mode="Markdown",
                            reply_markup=reply_markup
                        )
                else:
                    await context.bot.send_message(
                        chat_id=chat_id,
                        text=detalhes_texto,
                        parse_mode="Markdown",
                        reply_markup=reply_markup
                    )
    except Exception as e:
        logger.error(f"Erro ao tratar callback query: {e}")
    finally:
        stop_typing_event.set()
        await typing_task

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Recebe buscas por texto e decide se processa pesquisas de mídia ou ações de menu."""
    chat_id = update.effective_chat.id
    text = update.message.text
    
    # Tratamento rápido do teclado permanente
    if text == "🔥 Filmes em Alta":
        await apresentar_tendencias(update, context, "movie")
        return
    elif text == "📺 Séries em Alta":
        await apresentar_tendencias(update, context, "tv")
        return
    elif text == "🎬 Buscar Filme ou Série":
        await update.message.reply_text(
            "✍️ Qual filme ou série você deseja assistir? Digite o nome aqui embaixo!"
        )
        return
        
    # Inicializa busca em background
    stop_typing_event = asyncio.Event()
    typing_task = asyncio.create_task(manter_digitando(chat_id, context, stop_typing_event))
    
    try:
        # Busca direta no TMDb
        conteudo = await buscar_conteudo_tmdb(text)
        
        if not conteudo:
            await update.message.reply_text(
                f"🔍 Não consegui encontrar nenhum filme ou série com o nome *'{text}'*.\n"
                "Verifique a ortografia ou tente com outro título!", 
                parse_mode="Markdown"
            )
            return
            
        url_player = f"{PLAYER_BASE_URL}?tipo={conteudo['tipo']}&id={conteudo['id']}"
        
        # Botões interativos: Assistir e Recomendados correspondentes
        keyboard = [
            [
                InlineKeyboardButton("🍿 Assistir", url=url_player),
                InlineKeyboardButton("✨ Recomendados", callback_data=f"recomendar:{conteudo['tipo']}:{conteudo['id']}")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        nota_formatada = f"{conteudo['nota']:.1f}" if isinstance(conteudo['nota'], (int, float)) else str(conteudo['nota'])
        detalhes_texto = (
            f"🎬 *{conteudo['titulo']}*\n"
            f"📅 *Lançamento:* {conteudo['lancamento']}\n"
            f"⭐ *Nota:* {nota_formatada}/10\n\n"
            f"📝 *Sinopse:*\n{conteudo['sinopse']}"
        )
        
        if conteudo["poster"]:
            try:
                await context.bot.send_photo(
                    chat_id=chat_id,
                    photo=conteudo["poster"],
                    caption=detalhes_texto[:1024],
                    parse_mode="Markdown",
                    reply_markup=reply_markup
                )
            except Exception as e:
                logger.error(f"Erro ao enviar pôster: {e}")
                await update.message.reply_text(
                    detalhes_texto, 
                    parse_mode="Markdown", 
                    reply_markup=reply_markup
                )
        else:
            await update.message.reply_text(
                detalhes_texto, 
                parse_mode="Markdown", 
                reply_markup=reply_markup
            )
            
    finally:
        stop_typing_event.set()
        await typing_task

# ==========================================
# INICIALIZAÇÃO DO BOT
# ==========================================

def main():
    """Inicia o CineBot."""
    app = Application.builder().token(TELEGRAM_TOKEN).build()

    # Registro de Comandos básicos
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_ajuda))
    app.add_handler(CommandHandler("ajuda", cmd_ajuda))
    
    # Tratamento de botões de callback_data (Cliques inline)
    app.add_handler(CallbackQueryHandler(handle_callback_query))
    
    # Handler para mensagens de texto (Entradas do usuário)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("🍿 CineBot Multiusuário de Busca por Imagens está online!")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()

