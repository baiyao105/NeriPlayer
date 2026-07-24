package moe.ouom.neriplayer.util.media

import moe.ouom.neriplayer.core.player.PlayerManager
import moe.ouom.neriplayer.data.model.SongItem
import moe.ouom.neriplayer.data.platform.youtube.extractYouTubeMusicVideoId

internal fun buildRemoteSongShareUrl(originalSong: SongItem, queue: List<SongItem>): String {
    extractYouTubeMusicVideoId(originalSong.mediaUri)?.let { videoId ->
        return "https://music.youtube.com/watch?v=$videoId"
    }

    if (originalSong.album.startsWith(PlayerManager.BILI_SOURCE_TAG)) {
        val videoParts = queue.filter {
            it.id == originalSong.id && it.album.startsWith(PlayerManager.BILI_SOURCE_TAG)
        }
        if (videoParts.size > 1) {
            val pageIndex = videoParts.indexOfFirst { it.album == originalSong.album }
            val pageNumber = pageIndex + 1
            if (pageIndex != -1) {
                return "https://www.bilibili.com/video/av${originalSong.id}/?p=${pageNumber}"
            }
        }
        return "https://www.bilibili.com/video/av${originalSong.id}"
    }

    val mediaUri = originalSong.mediaUri
    return when {
        originalSong.album.startsWith(PlayerManager.NETEASE_SOURCE_TAG) ->
            "https://music.163.com/#/song?id=${originalSong.id}"
        !mediaUri.isNullOrBlank() &&
                (mediaUri.startsWith("https://") || mediaUri.startsWith("http://")) -> mediaUri
        else -> "https://music.163.com/#/song?id=${originalSong.id}"
    }
}