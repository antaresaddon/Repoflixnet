# -*- coding: utf-8 -*-
# ------------------------------------------------------------
# XBMC Library Tools
# ------------------------------------------------------------

import os
import threading
import time
import urllib2

import xbmc
from core import filetools
from core import jsontools
from platformcode import config, logger
from platformcode import platformtools


def mark_auto_as_watched(item):
    def mark_as_watched_subThread(item):
        logger.info()
        # logger.debug("item:\n" + item.tostring('\n'))

        condicion = config.get_setting("watched_setting", "videolibrary")

        time_limit = time.time() + 30
        while not platformtools.is_playing() and time.time() < time_limit:
            time.sleep(1)

        sync_with_trakt = False

        while platformtools.is_playing():
            tiempo_actual = xbmc.Player().getTime()
            totaltime = xbmc.Player().getTotalTime()

            mark_time = 0
            if condicion == 0:  # '5 minutos'
                mark_time = 300
            elif condicion == 1:  # '30%'
                mark_time = totaltime * 0.3
            elif condicion == 2:  # '50%'
                mark_time = totaltime * 0.5
            elif condicion == 3:  # '80%'
                mark_time = totaltime * 0.8
            elif condicion == 4:  # '0 seg'
                mark_time = -1

            # logger.debug(str(tiempo_actual))
            # logger.debug(str(mark_time))

            if tiempo_actual > mark_time:
                logger.debug("marcado")
                item.playcount = 1
                sync_with_trakt = True
                from channels import videolibrary
                videolibrary.mark_content_as_watched(item)
                break

            time.sleep(30)

        # Sincronizacion silenciosa con Trakt
        if sync_with_trakt:
            if config.get_setting("sync_trakt_watched", "videolibrary"):
                sync_trakt_kodi()

                # logger.debug("Fin del hilo")

    # Si esta configurado para marcar como visto
    if config.get_setting("mark_as_watched", "videolibrary"):
        threading.Thread(target=mark_as_watched_subThread, args=[item]).start()


def sync_trakt_addon(path_folder):
    """
       Actualiza los valores de episodios vistos si
    """
    logger.info()
    # si existe el addon hacemos la busqueda
    if xbmc.getCondVisibility('System.HasAddon("script.trakt")'):
        # importamos dependencias
        paths = ["special://home/addons/script.module.dateutil/lib/", "special://home/addons/script.module.six/lib/",
                 "special://home/addons/script.module.arrow/lib/", "special://home/addons/script.module.trakt/lib/",
                 "special://home/addons/script.trakt/"]

        for path in paths:
            import sys
            sys.path.append(xbmc.translatePath(path))

        # se obtiene las series vistas
        try:
            from resources.lib.traktapi import traktAPI
            traktapi = traktAPI()
        except:
            return

        shows = traktapi.getShowsWatched({})
        shows = shows.items()

        # obtenemos el id de la serie para comparar
        import re
        _id = re.findall("\[(.*?)\]", path_folder, flags=re.DOTALL)[0]
        logger.debug("el id es %s" % _id)

        if "tt" in _id:
            type_id = "imdb"
        elif "tvdb_" in _id:
            _id = _id.strip("tvdb_")
            type_id = "tvdb"
        elif "tmdb_" in _id:
            type_id = "tmdb"
            _id = _id.strip("tmdb_")
        else:
            logger.error("No hay _id de la serie")
            return

        # obtenemos los valores de la serie
        from core import videolibrarytools
        tvshow_file = filetools.join(path_folder, "tvshow.nfo")
        head_nfo, serie = videolibrarytools.read_nfo(tvshow_file)

        # buscamos en las series de trakt
        for show in shows:
            show_aux = show[1].to_dict()

            try:
                _id_trakt = show_aux['ids'].get(type_id, None)
                # logger.debug("ID ES %s" % _id_trakt)
                if _id_trakt:
                    if _id == _id_trakt:
                        logger.debug("ENCONTRADO!! %s" % show_aux)

                        # creamos el diccionario de trakt para la serie encontrada con el valor que tiene "visto"
                        dict_trakt_show = {}

                        for idx_season, season in enumerate(show_aux['seasons']):
                            for idx_episode, episode in enumerate(show_aux['seasons'][idx_season]['episodes']):
                                sea_epi = "%sx%s" % (show_aux['seasons'][idx_season]['number'],
                                                     str(show_aux['seasons'][idx_season]['episodes'][idx_episode][
                                                             'number']).zfill(2))

                                dict_trakt_show[sea_epi] = show_aux['seasons'][idx_season]['episodes'][idx_episode][
                                    'watched']
                        logger.debug("dict_trakt_show %s " % dict_trakt_show)

                        # obtenemos las keys que son episodios
                        regex_epi = re.compile('\d+x\d+')
                        keys_episodes = [key for key in serie.library_playcounts if regex_epi.match(key)]
                        # obtenemos las keys que son temporadas
                        keys_seasons = [key for key in serie.library_playcounts if 'season ' in key]
                        # obtenemos los numeros de las keys temporadas
                        seasons = [key.strip('season ') for key in keys_seasons]

                        # marcamos los episodios vistos
                        for k in keys_episodes:
                            serie.library_playcounts[k] = dict_trakt_show.get(k, 0)

                        for season in seasons:
                            episodios_temporada = 0
                            episodios_vistos_temporada = 0

                            # obtenemos las keys de los episodios de una determinada temporada
                            keys_season_episodes = [key for key in keys_episodes if key.startswith("%sx" % season)]

                            for k in keys_season_episodes:
                                episodios_temporada += 1
                                if serie.library_playcounts[k] > 0:
                                    episodios_vistos_temporada += 1

                            # se comprueba que si todos los episodios están vistos, se marque la temporada como vista
                            if episodios_temporada == episodios_vistos_temporada:
                                serie.library_playcounts.update({"season %s" % season: 1})

                        temporada = 0
                        temporada_vista = 0

                        for k in keys_seasons:
                            temporada += 1
                            if serie.library_playcounts[k] > 0:
                                temporada_vista += 1

                        # se comprueba que si todas las temporadas están vistas, se marque la serie como vista
                        if temporada == temporada_vista:
                            serie.library_playcounts.update({serie.title: 1})

                        logger.debug("los valores nuevos %s " % serie.library_playcounts)
                        filetools.write(tvshow_file, head_nfo + serie.tojson())

                        break
                    else:
                        continue

                else:
                    logger.error("no se ha podido obtener el id, trakt tiene: %s" % show_aux['ids'])

            except:
                import traceback
                logger.error(traceback.format_exc())


def sync_trakt_kodi(silent=True):
    # Para que la sincronizacion no sea silenciosa vale con silent=False
    if xbmc.getCondVisibility('System.HasAddon("script.trakt")'):
        notificacion = True
        if (not config.get_setting("sync_trakt_notification", "videolibrary") and
                platformtools.is_playing()):
            notificacion = False

        xbmc.executebuiltin('RunScript(script.trakt,action=sync,silent=%s)' % silent)
        logger.info("Sincronizacion con Trakt iniciada")

        if notificacion:
            platformtools.dialog_notification("Alfa",
                                              "Sincronizacion con Trakt iniciada",
                                              icon=0,
                                              time=2000)


def mark_content_as_watched_on_kodi(item, value=1):
    """
    marca el contenido como visto o no visto en la libreria de Kodi
    @type item: item
    @param item: elemento a marcar
    @type value: int
    @param value: >0 para visto, 0 para no visto
    """
    logger.info()
    # logger.debug("item:\n" + item.tostring('\n'))
    payload_f = ''

    if item.contentType == "movie":
        movieid = 0
        payload = {"jsonrpc": "2.0", "method": "VideoLibrary.GetMovies",
                   "params": {"properties": ["title", "playcount", "originaltitle", "file"]},
                   "id": 1}

        data = get_data(payload)
        if 'result' in data and "movies" in data['result']:

            filename = filetools.basename(item.strm_path)
            head, tail = filetools.split(filetools.split(item.strm_path)[0])
            path = filetools.join(tail, filename)

            for d in data['result']['movies']:
                if d['file'].replace("/", "\\").endswith(path.replace("/", "\\")):
                    # logger.debug("marco la pelicula como vista")
                    movieid = d['movieid']
                    break

        if movieid != 0:
            payload_f = {"jsonrpc": "2.0", "method": "VideoLibrary.SetMovieDetails", "params": {
                "movieid": movieid, "playcount": value}, "id": 1}

    else:  # item.contentType != 'movie'
        episodeid = 0
        payload = {"jsonrpc": "2.0", "method": "VideoLibrary.GetEpisodes",
                   "params": {"properties": ["title", "playcount", "showtitle", "file", "tvshowid"]},
                   "id": 1}

        data = get_data(payload)
        if 'result' in data and "episodes" in data['result']:

            filename = filetools.basename(item.strm_path)
            head, tail = filetools.split(filetools.split(item.strm_path)[0])
            path = filetools.join(tail, filename)

            for d in data['result']['episodes']:

                if d['file'].replace("/", "\\").endswith(path.replace("/", "\\")):
                    # logger.debug("marco el episodio como visto")
                    episodeid = d['episodeid']
                    break

        if episodeid != 0:
            payload_f = {"jsonrpc": "2.0", "method": "VideoLibrary.SetEpisodeDetails", "params": {
                "episodeid": episodeid, "playcount": value}, "id": 1}

    if payload_f:
        # Marcar como visto
        data = get_data(payload_f)
        # logger.debug(str(data))
        if data['result'] != 'OK':
            logger.error("ERROR al poner el contenido como visto")


def mark_season_as_watched_on_kodi(item, value=1):
    """
        marca toda la temporada como vista o no vista en la libreria de Kodi
        @type item: item
        @param item: elemento a marcar
        @type value: int
        @param value: >0 para visto, 0 para no visto
        """
    logger.info()
    # logger.debug("item:\n" + item.tostring('\n'))

    # Solo podemos marcar la temporada como vista en la BBDD de Kodi si la BBDD es local,
    # en caso de compartir BBDD esta funcionalidad no funcionara
    if config.get_setting("db_mode", "videolibrary"):
        return

    if value == 0:
        value = 'Null'

    request_season = ''
    if item.contentSeason > -1:
        request_season = ' and c12= %s' % item.contentSeason

    tvshows_path = filetools.join(config.get_videolibrary_path(), config.get_setting("folder_tvshows"))
    item_path1 = "%" + item.path.replace("\\\\", "\\").replace(tvshows_path, "")
    if item_path1[:-1] != "\\":
        item_path1 += "\\"
    item_path2 = item_path1.replace("\\", "/")

    sql = 'update files set playCount= %s where idFile  in ' \
          '(select idfile from episode_view where strPath like "%s" or strPath like "%s"%s)' % \
          (value, item_path1, item_path2, request_season)

    execute_sql_kodi(sql)


def get_data(payload):
    """
    obtiene la información de la llamada JSON-RPC con la información pasada en payload
    @type payload: dict
    @param payload: data
    :return:
    """
    logger.info("payload: %s" % payload)
    # Required header for XBMC JSON-RPC calls, otherwise you'll get a 415 HTTP response code - Unsupported media type
    headers = {'content-type': 'application/json'}

    if config.get_setting("db_mode", "videolibrary"):
        try:
            try:
                xbmc_port = config.get_setting("xbmc_puerto", "videolibrary")
            except:
                xbmc_port = 0

            xbmc_json_rpc_url = "http://" + config.get_setting("xbmc_host", "videolibrary") + ":" + str(
                xbmc_port) + "/jsonrpc"
            req = urllib2.Request(xbmc_json_rpc_url, data=jsontools.dump(payload), headers=headers)
            f = urllib2.urlopen(req)
            response = f.read()
            f.close()

            logger.info("get_data: response %s" % response)
            data = jsontools.load(response)
        except Exception, ex:
            template = "An exception of type %s occured. Arguments:\n%r"
            message = template % (type(ex).__name__, ex.args)
            logger.error("error en xbmc_json_rpc_url: %s" % message)
            data = ["error"]
    else:
        try:
            data = jsontools.load(xbmc.executeJSONRPC(jsontools.dump(payload)))
        except Exception, ex:
            template = "An exception of type %s occured. Arguments:\n%r"
            message = template % (type(ex).__name__, ex.args)
            logger.error("error en xbmc.executeJSONRPC: %s" % message)
            data = ["error"]

    logger.info("data: %s" % data)

    return data


def update(folder_content=config.get_setting("folder_tvshows"), folder=""):
    """
    Actualiza la libreria dependiendo del tipo de contenido y la ruta que se le pase.

    @type folder_content: str
    @param folder_content: tipo de contenido para actualizar, series o peliculas
    @type folder: str
    @param folder: nombre de la carpeta a escanear.
    """
    logger.info(folder)

    payload = {
        "jsonrpc": "2.0",
        "method": "VideoLibrary.Scan",
        "id": 1
    }

    if folder:
        videolibrarypath = config.get_videolibrary_config_path()

        if folder.endswith('/') or folder.endswith('\\'):
            folder = folder[:-1]

        update_path = None

        if videolibrarypath.startswith("special:"):
            if videolibrarypath.endswith('/'):
                videolibrarypath = videolibrarypath[:-1]
            update_path = videolibrarypath + "/" + folder_content + "/" + folder + "/"
        else:
            update_path = filetools.join(videolibrarypath, folder_content, folder) + "/"

        payload["params"] = {"directory": update_path}

    while xbmc.getCondVisibility('Library.IsScanningVideo()'):
        xbmc.sleep(500)

    data = get_data(payload)


def clean(mostrar_dialogo=False):
    """
    limpia la libreria de elementos que no existen
    @param mostrar_dialogo: muestra el cuadro de progreso mientras se limpia la videoteca
    @type mostrar_dialogo: bool
    """
    logger.info()
    payload = {"jsonrpc": "2.0", "method": "VideoLibrary.Clean", "id": 1,
               "params": {"showdialogs": mostrar_dialogo}}
    data = get_data(payload)

    if data.get('result', False) == 'OK':
        return True

    return False


def search_library_path():
    sql = 'SELECT strPath FROM path WHERE strPath LIKE "special://%/plugin.video.alfa/library/" AND idParentPath ISNULL'
    nun_records, records = execute_sql_kodi(sql)
    if nun_records >= 1:
        logger.debug(records[0][0])
        return records[0][0]
    return None


def set_content(content_type, silent=False):
    """
    Procedimiento para auto-configurar la videoteca de kodi con los valores por defecto
    @type content_type: str ('movie' o 'tvshow')
    @param content_type: tipo de contenido para configurar, series o peliculas
    """
    continuar = True
    msg_text = ""
    videolibrarypath = config.get_setting("videolibrarypath")

    if content_type == 'movie':
        if not xbmc.getCondVisibility('System.HasAddon(metadata.themoviedb.org)'):
            if not silent:
                # Preguntar si queremos instalar metadata.themoviedb.org
                install = platformtools.dialog_yesno("The Movie Database",
                                                     "No se ha encontrado el Scraper de películas de TheMovieDB.",
                                                     "¿Desea instalarlo ahora?")
            else:
                install = True

            if install:
                try:
                    # Instalar metadata.themoviedb.org
                    xbmc.executebuiltin('xbmc.installaddon(metadata.themoviedb.org)', True)
                    logger.info("Instalado el Scraper de películas de TheMovieDB")
                except:
                    pass

            continuar = (install and xbmc.getCondVisibility('System.HasAddon(metadata.themoviedb.org)'))
            if not continuar:
                msg_text = "The Movie Database no instalado."

    else:  # SERIES
        # Instalar The TVDB
        if not xbmc.getCondVisibility('System.HasAddon(metadata.tvdb.com)'):
            if not silent:
                # Preguntar si queremos instalar metadata.tvdb.com
                install = platformtools.dialog_yesno("The TVDB",
                                                     "No se ha encontrado el Scraper de series de The TVDB.",
                                                     "¿Desea instalarlo ahora?")
            else:
                install = True

            if install:
                try:
                    # Instalar metadata.tvdb.com
                    xbmc.executebuiltin('xbmc.installaddon(metadata.tvdb.com)', True)
                    logger.info("Instalado el Scraper de series de The TVDB")
                except:
                    pass

            continuar = (install and xbmc.getCondVisibility('System.HasAddon(metadata.tvdb.com)'))
            if not continuar:
                msg_text = "The TVDB no instalado."

        # Instalar TheMovieDB
        if continuar and not xbmc.getCondVisibility('System.HasAddon(metadata.tvshows.themoviedb.org)'):
            continuar = False
            if not silent:
                # Preguntar si queremos instalar metadata.tvshows.themoviedb.org
                install = platformtools.dialog_yesno("The Movie Database",
                                                     "No se ha encontrado el Scraper de series de TheMovieDB.",
                                                     "¿Desea instalarlo ahora?")
            else:
                install = True

            if install:
                try:
                    # Instalar metadata.tvshows.themoviedb.org
                    # 1º Probar desde el repositorio ...
                    xbmc.executebuiltin('xbmc.installaddon(metadata.tvshows.themoviedb.org)', True)
                    if not xbmc.getCondVisibility('System.HasAddon(metadata.tvshows.themoviedb.org)'):
                        # ...si no funciona descargar e instalar desde la web
                        url = "http://mirrors.kodi.tv/addons/jarvis/metadata.tvshows.themoviedb.org/metadata.tvshows.themoviedb.org-1.3.1.zip"
                        path_down = xbmc.translatePath(
                            "special://home/addons/packages/metadata.tvshows.themoviedb.org-1.3.1.zip")
                        path_unzip = xbmc.translatePath("special://home/addons/")
                        header = ("User-Agent",
                                  "Kodi/15.2 (Windows NT 10.0; WOW64) App_Bitness/32 Version/15.2-Git:20151019-02e7013")

                        from core import downloadtools
                        from core import ziptools

                        downloadtools.downloadfile(url, path_down, continuar=True, headers=[header])
                        unzipper = ziptools.ziptools()
                        unzipper.extract(path_down, path_unzip)
                        xbmc.executebuiltin('UpdateLocalAddons')

                    strSettings = '<settings>\n' \
                                  '    <setting id="fanart" value="true" />\n' \
                                  '    <setting id="keeporiginaltitle" value="false" />\n' \
                                  '    <setting id="language" value="es" />\n' \
                                  '</settings>'
                    path_settings = xbmc.translatePath(
                        "special://profile/addon_data/metadata.tvshows.themoviedb.org/settings.xml")
                    tv_themoviedb_addon_path = filetools.dirname(path_settings)
                    if not filetools.exists(tv_themoviedb_addon_path):
                        filetools.mkdir(tv_themoviedb_addon_path)
                    if filetools.write(path_settings, strSettings):
                        continuar = True

                except:
                    pass

            continuar = (install and continuar)
            if not continuar:
                msg_text = "The Movie Database no instalado."

    idPath = 0
    idParentPath = 0
    if continuar:
        continuar = False

        # Buscamos el idPath
        sql = 'SELECT MAX(idPath) FROM path'
        nun_records, records = execute_sql_kodi(sql)
        if nun_records == 1:
            idPath = records[0][0] + 1

        sql_videolibrarypath = videolibrarypath
        if sql_videolibrarypath.startswith("special://"):
            sql_videolibrarypath = sql_videolibrarypath.replace('/profile/', '/%/').replace('/home/userdata/', '/%/')
            sep = '/'
        elif sql_videolibrarypath.startswith("smb://"):
            sep = '/'
        else:
            sep = os.sep

        if not sql_videolibrarypath.endswith(sep):
            sql_videolibrarypath += sep

        # Buscamos el idParentPath
        sql = 'SELECT idPath, strPath FROM path where strPath LIKE "%s"' % sql_videolibrarypath
        nun_records, records = execute_sql_kodi(sql)
        if nun_records == 1:
            idParentPath = records[0][0]
            videolibrarypath = records[0][1][:-1]
            continuar = True
        else:
            # No existe videolibrarypath en la BD: la insertamos
            sql_videolibrarypath = videolibrarypath
            if not sql_videolibrarypath.endswith(sep):
                sql_videolibrarypath += sep

            sql = 'INSERT INTO path (idPath, strPath,  scanRecursive, useFolderNames, noUpdate, exclude) VALUES ' \
                  '(%s, "%s", 0, 0, 0, 0)' % (idPath, sql_videolibrarypath)
            nun_records, records = execute_sql_kodi(sql)
            if nun_records == 1:
                continuar = True
                idParentPath = idPath
                idPath += 1
            else:
                msg_text = "Error al fijar videolibrarypath en BD"

    if continuar:
        continuar = False

        # Fijamos strContent, strScraper, scanRecursive y strSettings
        if content_type == 'movie':
            strContent = 'movies'
            strScraper = 'metadata.themoviedb.org'
            scanRecursive = 2147483647
            strSettings = "<settings><setting id='RatingS' value='TMDb' /><setting id='certprefix' value='Rated ' />" \
                          "<setting id='fanart' value='true' /><setting id='keeporiginaltitle' value='false' />" \
                          "<setting id='language' value='es' /><setting id='tmdbcertcountry' value='us' />" \
                          "<setting id='trailer' value='true' /></settings>"
            strActualizar = "¿Desea configurar este Scraper en español como opción por defecto para películas?"
            if not videolibrarypath.endswith(sep):
                videolibrarypath += sep
            strPath = videolibrarypath + config.get_setting("folder_movies") + sep
        else:
            strContent = 'tvshows'
            strScraper = 'metadata.tvdb.com'
            scanRecursive = 0
            strSettings = "<settings><setting id='RatingS' value='TheTVDB' />" \
                          "<setting id='absolutenumber' value='false' />" \
                          "<setting id='dvdorder' value='false' />" \
                          "<setting id='fallback' value='true' />" \
                          "<setting id='fanart' value='true' />" \
                          "<setting id='language' value='es' /></settings>"
            strActualizar = "¿Desea configurar este Scraper en español como opción por defecto para series?"
            if not videolibrarypath.endswith(sep):
                videolibrarypath += sep
            strPath = videolibrarypath + config.get_setting("folder_tvshows") + sep

        logger.info("%s: %s" % (content_type, strPath))
        # Comprobamos si ya existe strPath en la BD para evitar duplicados
        sql = 'SELECT idPath FROM path where strPath="%s"' % strPath
        nun_records, records = execute_sql_kodi(sql)
        sql = ""
        if nun_records == 0:
            # Insertamos el scraper
            sql = 'INSERT INTO path (idPath, strPath, strContent, strScraper, scanRecursive, useFolderNames, ' \
                  'strSettings, noUpdate, exclude, idParentPath) VALUES (%s, "%s", "%s", "%s", %s, 0, ' \
                  '"%s", 0, 0, %s)' % (
                      idPath, strPath, strContent, strScraper, scanRecursive, strSettings, idParentPath)
        else:
            if not silent:
                # Preguntar si queremos configurar themoviedb.org como opcion por defecto
                actualizar = platformtools.dialog_yesno("The TVDB", strActualizar)
            else:
                actualizar = True

            if actualizar:
                # Actualizamos el scraper
                idPath = records[0][0]
                sql = 'UPDATE path SET strContent="%s", strScraper="%s", scanRecursive=%s, strSettings="%s" ' \
                      'WHERE idPath=%s' % (strContent, strScraper, scanRecursive, strSettings, idPath)

        if sql:
            nun_records, records = execute_sql_kodi(sql)
            if nun_records == 1:
                continuar = True

        if not continuar:
            msg_text = "Error al configurar el scraper en la BD."

    if not continuar:
        heading = "Videoteca %s no configurada" % content_type
    elif content_type == 'SERIES' and not xbmc.getCondVisibility(
            'System.HasAddon(metadata.tvshows.themoviedb.org)'):
        heading = "Videoteca %s configurada" % content_type
        msg_text = "Es necesario reiniciar Kodi para que los cambios surtan efecto."
    else:
        heading = "Videoteca %s configurada" % content_type
        msg_text = "Felicidades la videoteca de Kodi ha sido configurada correctamente."
    platformtools.dialog_notification(heading, msg_text, icon=1, time=10000)
    logger.info("%s: %s" % (heading, msg_text))


def execute_sql_kodi(sql):
    """
    Ejecuta la consulta sql contra la base de datos de kodi
    @param sql: Consulta sql valida
    @type sql: str
    @return: Numero de registros modificados o devueltos por la consulta
    @rtype nun_records: int
    @return: lista con el resultado de la consulta
    @rtype records: list of tuples
    """
    logger.info()
    file_db = ""
    nun_records = 0
    records = None

    # Buscamos el archivo de la BBDD de videos segun la version de kodi
    video_db = config.get_platform(True)['video_db']
    if video_db:
        file_db = filetools.join(xbmc.translatePath("special://userdata/Database"), video_db)

    # metodo alternativo para localizar la BBDD
    if not file_db or not filetools.exists(file_db):
        file_db = ""
        for f in filetools.listdir(xbmc.translatePath("special://userdata/Database")):
            path_f = filetools.join(xbmc.translatePath("special://userdata/Database"), f)

            if filetools.isfile(path_f) and f.lower().startswith('myvideos') and f.lower().endswith('.db'):
                file_db = path_f
                break

    if file_db:
        logger.info("Archivo de BD: %s" % file_db)
        conn = None
        try:
            import sqlite3
            conn = sqlite3.connect(file_db)
            cursor = conn.cursor()

            logger.info("Ejecutando sql: %s" % sql)
            cursor.execute(sql)
            conn.commit()

            records = cursor.fetchall()
            if sql.lower().startswith("select"):
                nun_records = len(records)
                if nun_records == 1 and records[0][0] is None:
                    nun_records = 0
                    records = []
            else:
                nun_records = conn.total_changes

            conn.close()
            logger.info("Consulta ejecutada. Registros: %s" % nun_records)

        except:
            logger.error("Error al ejecutar la consulta sql")
            if conn:
                conn.close()

    else:
        logger.debug("Base de datos no encontrada")

    return nun_records, records


def add_sources(path):
    logger.info()
    from xml.dom import minidom

    SOURCES_PATH = xbmc.translatePath("special://userdata/sources.xml")

    if os.path.exists(SOURCES_PATH):
        xmldoc = minidom.parse(SOURCES_PATH)
    else:
        # Crear documento
        xmldoc = minidom.Document()
        nodo_sources = xmldoc.createElement("sources")

        for type in ['programs', 'video', 'music', 'picture', 'files']:
            nodo_type = xmldoc.createElement(type)
            element_default = xmldoc.createElement("default")
            element_default.setAttribute("pathversion", "1")
            nodo_type.appendChild(element_default)
            nodo_sources.appendChild(nodo_type)
        xmldoc.appendChild(nodo_sources)

    # Buscamos el nodo video
    nodo_video = xmldoc.childNodes[0].getElementsByTagName("video")[0]

    # Buscamos el path dentro de los nodos_path incluidos en el nodo_video
    nodos_paths = nodo_video.getElementsByTagName("path")
    list_path = [p.firstChild.data for p in nodos_paths]
    logger.debug(list_path)
    if path in list_path:
        logger.debug("La ruta %s ya esta en sources.xml" % path)
        return
    logger.debug("La ruta %s NO esta en sources.xml" % path)

    # Si llegamos aqui es por q el path no esta en sources.xml, asi q lo incluimos
    nodo_source = xmldoc.createElement("source")

    # Nodo <name>
    nodo_name = xmldoc.createElement("name")
    sep = os.sep
    if path.startswith("special://") or path.startswith("smb://"):
        sep = "/"
    name = path
    if path.endswith(sep):
        name = path[:-1]
    nodo_name.appendChild(xmldoc.createTextNode(name.rsplit(sep)[-1]))
    nodo_source.appendChild(nodo_name)

    # Nodo <path>
    nodo_path = xmldoc.createElement("path")
    nodo_path.setAttribute("pathversion", "1")
    nodo_path.appendChild(xmldoc.createTextNode(path))
    nodo_source.appendChild(nodo_path)

    # Nodo <allowsharing>
    nodo_allowsharing = xmldoc.createElement("allowsharing")
    nodo_allowsharing.appendChild(xmldoc.createTextNode('true'))
    nodo_source.appendChild(nodo_allowsharing)

    # Añadimos <source>  a <video>
    nodo_video.appendChild(nodo_source)

    # Guardamos los cambios
    filetools.write(SOURCES_PATH,
                    '\n'.join([x for x in xmldoc.toprettyxml().encode("utf-8").splitlines() if x.strip()]))


def ask_set_content(flag, silent=False):
    logger.info()
    logger.debug("videolibrary_kodi_flag %s" % config.get_setting("videolibrary_kodi_flag"))
    logger.debug("videolibrary_kodi %s" % config.get_setting("videolibrary_kodi"))

    def do_config():
        logger.debug("hemos aceptado")
        config.set_setting("videolibrary_kodi", True)
        set_content("movie", silent=True)
        set_content("tvshow", silent=True)
        add_sources(config.get_setting("videolibrarypath"))
        add_sources(config.get_setting("downloadpath"))

    if not silent:
        heading = "Alfa Auto-configuración"
        linea1 = "¿Desea que Alfa auto-configure la videoteca de Kodi?"
        linea2 = "Si pulsa 'No' podra hacerlo desde 'Configuración > Preferencia > Rutas'."
        if platformtools.dialog_yesno(heading, linea1, linea2):
            do_config()
        else:
            # no hemos aceptado
            config.set_setting("videolibrary_kodi", False)

    else:
        do_config()

    config.set_setting("videolibrary_kodi_flag", flag)
