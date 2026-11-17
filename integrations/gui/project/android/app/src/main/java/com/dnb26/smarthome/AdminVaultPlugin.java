package com.dnb26.smarthome;

import android.content.Context;
import android.content.SharedPreferences;
import android.security.keystore.KeyGenParameterSpec;
import android.security.keystore.KeyProperties;
import android.util.Base64;
import com.getcapacitor.JSObject;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.CapacitorPlugin;
import java.nio.charset.StandardCharsets;
import java.security.KeyStore;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;
import org.json.JSONObject;

/** Encrypts one backend-bound administrator credential with a non-exportable device key. */
@CapacitorPlugin(name = "AdminVault")
public class AdminVaultPlugin extends Plugin {
    private static final String KEY_ALIAS = "dnb26_admin_v1";

    private SharedPreferences preferences() {
        return getContext().getSharedPreferences("dnb26_admin_vault", Context.MODE_PRIVATE);
    }

    private SecretKey key(boolean create) throws Exception {
        KeyStore store = KeyStore.getInstance("AndroidKeyStore");
        store.load(null);
        if (store.containsAlias(KEY_ALIAS)) return (SecretKey) store.getKey(KEY_ALIAS, null);
        if (!create) throw new IllegalStateException("Device key unavailable");
        KeyGenerator generator = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore");
        generator.init(new KeyGenParameterSpec.Builder(KEY_ALIAS,
            KeyProperties.PURPOSE_ENCRYPT | KeyProperties.PURPOSE_DECRYPT)
            .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
            .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE).setKeySize(256).build());
        return generator.generateKey();
    }

    @PluginMethod
    public void set(PluginCall call) {
        String backend = call.getString("backend", "");
        String token = call.getString("token", "");
        if (backend.isEmpty() || token.isEmpty() || backend.length() > 2048 || token.length() > 4096) {
            call.reject("Invalid administrator configuration");
            return;
        }
        try {
            JSONObject payload = new JSONObject().put("backend", backend).put("token", token);
            Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
            cipher.init(Cipher.ENCRYPT_MODE, key(true));
            String encrypted = Base64.encodeToString(cipher.doFinal(payload.toString().getBytes(StandardCharsets.UTF_8)), Base64.NO_WRAP);
            String iv = Base64.encodeToString(cipher.getIV(), Base64.NO_WRAP);
            if (!preferences().edit().putString("ciphertext", encrypted).putString("iv", iv).commit()) {
                throw new IllegalStateException("Storage unavailable");
            }
            call.resolve();
        } catch (Exception exception) {
            call.reject("无法加密保存管理员权限，请重试");
        }
    }

    @PluginMethod
    public void get(PluginCall call) {
        String encrypted = preferences().getString("ciphertext", "");
        if (encrypted.isEmpty()) {
            call.resolve(new JSObject().put("token", ""));
            return;
        }
        try {
            byte[] iv = Base64.decode(preferences().getString("iv", ""), Base64.NO_WRAP);
            Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
            cipher.init(Cipher.DECRYPT_MODE, key(false), new GCMParameterSpec(128, iv));
            JSONObject payload = new JSONObject(new String(cipher.doFinal(Base64.decode(encrypted, Base64.NO_WRAP)), StandardCharsets.UTF_8));
            String token = payload.getString("backend").equals(call.getString("backend", "")) ? payload.getString("token") : "";
            call.resolve(new JSObject().put("token", token));
        } catch (Exception exception) {
            call.reject("无法恢复管理员权限，请在系统页重新授权");
        }
    }

    @PluginMethod
    public void clear(PluginCall call) {
        if (!preferences().edit().clear().commit()) {
            call.reject("无法清除管理员权限，请重试");
            return;
        }
        call.resolve();
    }
}
