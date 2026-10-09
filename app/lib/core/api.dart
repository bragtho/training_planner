import 'package:dio/dio.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

/// Backend-URL: per `--dart-define=API_URL=...` ueberschreibbar.
String get apiBaseUrl {
  const fromEnv = String.fromEnvironment('API_URL');
  if (fromEnv.isNotEmpty) return fromEnv;
  if (kIsWeb) {
    // Web-App ueber Tailscale/LAN geoeffnet: Backend liegt auf demselben Rechner.
    final host = Uri.base.host;
    if (host.isNotEmpty && host != 'localhost' && host != '127.0.0.1') {
      return Uri.base.scheme == 'https'
          ? Uri.base.origin // z. B. `tailscale serve` mit HTTPS
          : 'http://$host:8000';
    }
  }
  if (!kIsWeb && defaultTargetPlatform == TargetPlatform.android) {
    return 'http://10.0.2.2:8000'; // Android-Emulator -> Host-PC
  }
  return 'http://localhost:8000';
}

class TokenStore {
  static const _key = 'access_token';
  final _storage = const FlutterSecureStorage();

  Future<String?> read() async {
    try {
      return await _storage.read(key: _key);
    } catch (_) {
      return null;
    }
  }

  Future<void> write(String? token) async {
    try {
      if (token == null) {
        await _storage.delete(key: _key);
      } else {
        await _storage.write(key: _key, value: token);
      }
    } catch (_) {}
  }

  static const _urlKey = 'api_url';

  /// Vom Nutzer gesetzte Server-Adresse (hat Vorrang vor [apiBaseUrl]).
  Future<String?> readUrl() async {
    try {
      return await _storage.read(key: _urlKey);
    } catch (_) {
      return null;
    }
  }

  Future<void> writeUrl(String? url) async {
    try {
      if (url == null || url.isEmpty) {
        await _storage.delete(key: _urlKey);
      } else {
        await _storage.write(key: _urlKey, value: url);
      }
    } catch (_) {}
  }
}

final tokenStoreProvider = Provider((_) => TokenStore());

/// Haengt den JWT an jede Anfrage; bei 401 wird [onUnauthorized] aufgerufen.
class ApiClient {
  ApiClient(this._tokens, {this.onUnauthorized}) {
    dio = Dio(BaseOptions(
      baseUrl: apiBaseUrl,
      connectTimeout: const Duration(seconds: 10),
      receiveTimeout: const Duration(seconds: 30),
    ));
    dio.interceptors.add(InterceptorsWrapper(
      onRequest: (o, h) async {
        final url = await _tokens.readUrl();
        if (url != null && url.isNotEmpty) o.baseUrl = url;
        final t = await _tokens.read();
        if (t != null) o.headers['Authorization'] = 'Bearer $t';
        h.next(o);
      },
      onError: (e, h) {
        if (e.response?.statusCode == 401 &&
            !e.requestOptions.path.startsWith('/auth/')) {
          onUnauthorized?.call();
        }
        h.next(e);
      },
    ));
  }

  final TokenStore _tokens;
  final void Function()? onUnauthorized;
  late final Dio dio;
}

String errorMessage(Object e) {
  if (e is DioException) {
    final d = e.response?.data;
    if (d is Map && d['detail'] is String) return d['detail'] as String;
    if (e.type == DioExceptionType.connectionError ||
        e.type == DioExceptionType.connectionTimeout) {
      return 'Backend nicht erreichbar (${e.requestOptions.baseUrl})';
    }
  }
  return 'Unerwarteter Fehler';
}
