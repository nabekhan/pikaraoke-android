package org.pikaraoke.tv;

import android.database.*;
import android.os.*;
import android.provider.DocumentsContract;
import android.provider.DocumentsProvider;
import android.webkit.MimeTypeMap;
import java.io.*;

/** Read-only SAF access: copy actual downloaded files with any document picker. */
public final class SongDocumentsProvider extends DocumentsProvider {
    private static final String[] ROOTS = {"root_id", "document_id", "title", "flags", "mime_types", "available_bytes"};
    private static final String[] DOCS = {"document_id", "_display_name", "mime_type", "flags", "_size", "last_modified"};
    @Override public boolean onCreate() { return true; }
    @Override public Cursor queryRoots(String[] projection) {
        MatrixCursor cursor = new MatrixCursor(projection != null ? projection : ROOTS);
        File root = AndroidPlatform.songs(getContext());
        MatrixCursor.RowBuilder row = cursor.newRow();
        row.add("root_id", "songs"); row.add("document_id", ""); row.add("title", "PiKaraoke songs");
        row.add("flags", DocumentsContract.Root.FLAG_LOCAL_ONLY); row.add("mime_types", "*/*"); row.add("available_bytes", root.getUsableSpace());
        return cursor;
    }
    private File file(String id) throws FileNotFoundException {
        try {
            File root = AndroidPlatform.songs(getContext()).getCanonicalFile();
            File file = new File(root, id).getCanonicalFile();
            if (!file.equals(root) && !file.getPath().startsWith(root.getPath() + File.separator)) throw new FileNotFoundException("Outside song library");
            if (!file.exists()) throw new FileNotFoundException("Song no longer exists");
            return file;
        } catch(IOException e) { throw new FileNotFoundException(e.getMessage()); }
    }
    private void add(MatrixCursor cursor, File file) throws FileNotFoundException {
        try {
            File root = AndroidPlatform.songs(getContext()).getCanonicalFile();
            String id = root.toPath().relativize(file.getCanonicalFile().toPath()).toString();
            String ext = MimeTypeMap.getFileExtensionFromUrl(file.getName());
            String mime = file.isDirectory() ? DocumentsContract.Document.MIME_TYPE_DIR : MimeTypeMap.getSingleton().getMimeTypeFromExtension(ext);
            MatrixCursor.RowBuilder row=cursor.newRow();
            row.add("document_id", id); row.add("_display_name", file.equals(root) ? "PiKaraoke songs" : file.getName());
            row.add("mime_type", mime == null ? "application/octet-stream" : mime); row.add("flags", 0);
            row.add("_size", file.length()); row.add("last_modified", file.lastModified());
        } catch(IOException e) { throw new FileNotFoundException(e.getMessage()); }
    }
    @Override public Cursor queryDocument(String id, String[] projection) throws FileNotFoundException {
        MatrixCursor cursor=new MatrixCursor(projection != null ? projection : DOCS); add(cursor,file(id)); return cursor;
    }
    @Override public Cursor queryChildDocuments(String id, String[] projection, String sortOrder) throws FileNotFoundException {
        MatrixCursor cursor=new MatrixCursor(projection != null ? projection : DOCS);
        File[] children=file(id).listFiles();
        if(children!=null) for(File child:children) if(!child.getName().endsWith(".part") && !child.getName().startsWith(".")) add(cursor,child);
        return cursor;
    }
    @Override public ParcelFileDescriptor openDocument(String id, String mode, CancellationSignal signal) throws FileNotFoundException {
        if (!"r".equals(mode)) throw new FileNotFoundException("Import files through PiKaraoke");
        return ParcelFileDescriptor.open(file(id), ParcelFileDescriptor.MODE_READ_ONLY);
    }
    @Override public boolean isChildDocument(String parent, String child) {
        try { return file(child).getPath().startsWith(file(parent).getPath() + File.separator); }
        catch(FileNotFoundException e) { return false; }
    }
}
