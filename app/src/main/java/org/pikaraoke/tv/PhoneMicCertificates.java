package org.pikaraoke.tv;

import android.content.Context;
import java.io.*;
import java.math.BigInteger;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.security.*;
import java.security.cert.*;
import java.security.spec.PKCS8EncodedKeySpec;
import java.util.*;
import org.bouncycastle.asn1.x500.X500Name;
import org.bouncycastle.asn1.x509.*;
import org.bouncycastle.cert.jcajce.*;
import org.bouncycastle.operator.jcajce.JcaContentSignerBuilder;
import org.json.JSONObject;

/** Private per-install CA. Only ca.crt is exposed to phones. */
public final class PhoneMicCertificates {
    private static final SecureRandom random = new SecureRandom();
    private PhoneMicCertificates() { }
    public static synchronized String ensure(Context context, String ip) throws Exception {
        File dir = new File(context.getNoBackupFilesDir(), "phone-mic-tls");
        if (!dir.isDirectory() && !dir.mkdirs()) throw new IOException("Cannot create microphone certificates");
        File caPem = new File(dir, "ca.pem"), caKey = new File(dir, "ca-key.pem");
        PrivateKey rootKey;
        X509Certificate root;
        if (!caPem.exists() && !caKey.exists()) {
            KeyPair pair = keyPair(); rootKey = pair.getPrivate();
            X500Name name = new X500Name("CN=PiKaraoke TV " + UUID.randomUUID().toString().substring(0, 8));
            JcaX509v3CertificateBuilder b = builder(name, name, pair.getPublic(), 3650);
            b.addExtension(org.bouncycastle.asn1.x509.Extension.basicConstraints, true, new BasicConstraints(0));
            b.addExtension(org.bouncycastle.asn1.x509.Extension.keyUsage, true,
                new KeyUsage(KeyUsage.keyCertSign | KeyUsage.cRLSign));
            root = sign(b, rootKey);
            write(caKey, pem("PRIVATE KEY", rootKey.getEncoded()));
            write(caPem, pem("CERTIFICATE", root.getEncoded()));
        } else {
            root = certificate(caPem);
            String value = new String(Files.readAllBytes(caKey.toPath()), StandardCharsets.US_ASCII)
                .replace("-----BEGIN PRIVATE KEY-----", "").replace("-----END PRIVATE KEY-----", "").replaceAll("\\s", "");
            rootKey = KeyFactory.getInstance("RSA").generatePrivate(new PKCS8EncodedKeySpec(Base64.getDecoder().decode(value)));
        }
        File certFile = new File(dir, "server.pem"), keyFile = new File(dir, "server-key.pem");
        File address = new File(dir, "address");
        boolean renew = !certFile.exists() || !keyFile.exists() || !address.exists()
            || !new String(Files.readAllBytes(address.toPath()), StandardCharsets.UTF_8).equals(ip);
        if (!renew) {
            try { certificate(certFile).checkValidity(new Date(System.currentTimeMillis() + 30L * 86400000)); }
            catch (CertificateException e) { renew = true; }
        }
        if (renew) {
            KeyPair server = keyPair();
            X500Name issuer = new X500Name(root.getSubjectX500Principal().getName());
            JcaX509v3CertificateBuilder b = builder(issuer, new X500Name("CN=PiKaraoke TV"), server.getPublic(), 365);
            b.addExtension(org.bouncycastle.asn1.x509.Extension.basicConstraints, true, new BasicConstraints(false));
            b.addExtension(org.bouncycastle.asn1.x509.Extension.keyUsage, true,
                new KeyUsage(KeyUsage.digitalSignature | KeyUsage.keyEncipherment));
            b.addExtension(org.bouncycastle.asn1.x509.Extension.extendedKeyUsage, false, new ExtendedKeyUsage(KeyPurposeId.id_kp_serverAuth));
            List<GeneralName> names = new ArrayList<>();
            names.add(new GeneralName(GeneralName.iPAddress, "127.0.0.1"));
            names.add(new GeneralName(GeneralName.dNSName, "localhost"));
            if (ip != null && !ip.equals("127.0.0.1")) names.add(new GeneralName(GeneralName.iPAddress, ip));
            b.addExtension(org.bouncycastle.asn1.x509.Extension.subjectAlternativeName, false,
                new GeneralNames(names.toArray(new GeneralName[0])));
            X509Certificate cert = sign(b, rootKey);
            cert.verify(root.getPublicKey());
            write(keyFile, pem("PRIVATE KEY", server.getPrivate().getEncoded()));
            write(certFile, pem("CERTIFICATE", cert.getEncoded()) + pem("CERTIFICATE", root.getEncoded()));
            write(address, ip);
        }
        File download = new File(dir, "ca.crt");
        Files.write(download.toPath(), root.getEncoded());
        StringBuilder fingerprint = new StringBuilder();
        for (byte value : MessageDigest.getInstance("SHA-256").digest(root.getEncoded())) {
            if (fingerprint.length() > 0) fingerprint.append(':');
            fingerprint.append(String.format(Locale.ROOT, "%02X", value & 255));
        }
        return new JSONObject().put("cert", certFile.getAbsolutePath()).put("key", keyFile.getAbsolutePath())
            .put("ca", download.getAbsolutePath()).put("fingerprint", fingerprint.toString()).toString();
    }
    private static KeyPair keyPair() throws GeneralSecurityException {
        KeyPairGenerator g = KeyPairGenerator.getInstance("RSA"); g.initialize(2048, random); return g.generateKeyPair();
    }
    private static JcaX509v3CertificateBuilder builder(X500Name issuer, X500Name subject, PublicKey key, int days) {
        long now = System.currentTimeMillis();
        return new JcaX509v3CertificateBuilder(issuer, new BigInteger(159, random).add(BigInteger.ONE),
            new Date(now - 86400000L), new Date(now + days * 86400000L), subject, key);
    }
    private static X509Certificate sign(JcaX509v3CertificateBuilder b, PrivateKey key) throws Exception {
        return new JcaX509CertificateConverter().getCertificate(b.build(new JcaContentSignerBuilder("SHA256withRSA").build(key)));
    }
    private static X509Certificate certificate(File file) throws Exception {
        try (InputStream input = new FileInputStream(file)) {
            return (X509Certificate)CertificateFactory.getInstance("X.509").generateCertificate(input);
        }
    }
    private static String pem(String type, byte[] data) {
        return "-----BEGIN " + type + "-----\n" + Base64.getMimeEncoder(64, new byte[]{10}).encodeToString(data)
            + "\n-----END " + type + "-----\n";
    }
    private static void write(File file, String text) throws IOException {
        File temp = new File(file.getParentFile(), file.getName() + ".tmp");
        Files.write(temp.toPath(), text.getBytes(StandardCharsets.UTF_8));
        temp.setReadable(false, false); temp.setWritable(false, false);
        temp.setReadable(true, true); temp.setWritable(true, true);
        if (!temp.renameTo(file)) throw new IOException("Cannot save microphone certificate");
    }
}
